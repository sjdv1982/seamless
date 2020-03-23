from zipfile import ZipFile
from io import BytesIO
from ..core import context, cell
from ..core.protocol.calculate_checksum import checksum_cache
from . import copying
from copy import deepcopy

class StaticContext:
    _parent_path = None

    @classmethod
    def from_graph(cls, graph, *, manager=None):
        nodes0 = graph["nodes"]
        nodes = {tuple(node["path"]):node for node in nodes0}
        connections = graph["connections"]
        params = graph.get("params", {})
        return cls(nodes, connections, params, manager=manager)

    def __init__(self, nodes, connections, params={}, *, manager=None):
        from seamless.core.manager import Manager
        self._nodes = nodes
        self._connections = connections
        self._params = params
        if manager is not None:            
            assert isinstance(manager, Manager), type(manager)
            self._manager = manager
        else:
            self._manager = Manager()
        self.root = context(toplevel=True,manager=self._manager)

    def get_graph(self):
        graph = {}
        graph["nodes"] = deepcopy(list(self._nodes.values()))
        graph["connections"] = deepcopy(self._connections)
        graph["params"] = deepcopy(self._params)
        return graph

    def add_zip(self, zip):
        if isinstance(zip, bytes):
            archive = BytesIO(zip)
            zipfile = ZipFile(archive, "r")
        elif isinstance(zip, str):
            zipfile = ZipFile(zip, "r")
        elif isinstance(zip, ZipFile):
            zipfile = zip
        else:
            raise TypeError(type(zip))        
        return copying.add_zip(self._manager, zipfile)

    
    def __getattr__(self, attr):
        parent_path = self._parent_path
        if parent_path is None:
            path = (attr,)
        else:
            path = parent_path + (attr,)
        if path not in self._nodes:
            raise AttributeError(attr)
        node = self._nodes[path]
        t = node["type"]
        if t == "cell":
            if node["celltype"] == "structured":
                return StructuredCellWrapper(
                    self._manager, node
                )
            else:
                checksum = node.get("checksum", {}).get("value")                
                return SimpleCellWrapper(
                    self._manager, node,
                    node["celltype"], checksum
                )
        elif t == "context":
            l = len(path)
            def in_path(p):
                if len(p) < l:
                    return False
                return p[:l] == path
            nodes = { k:v for k,v in self._nodes.items() if in_path(k)}            
            connections = [c for c in self._connections \
                if in_path(c["source"]) or in_path(c["target"])
            ]
            result = StaticContext(
                nodes, connections, 
                manager=self._manager
            )
            result._parent_path = path
            return result
        elif t == "transformer":
            return TransformerWrapper(
                self._manager, node
            )
        elif t == "reactor":
            raise NotImplementedError(t)
        elif t == "macro":
            raise NotImplementedError(t)
        else:
            raise TypeError(t)

class WrapperBase:
    def __init__(self, manager, node):
        self._manager = manager
        self._node = node

class SimpleCellWrapper(WrapperBase):

    def __init__(self, manager, node, celltype, checksum):
        super().__init__(manager, node)
        root = self._manager.last_ctx()
        assert root is not None
        self._root = root
        self._celltype = celltype
        assert checksum is None or isinstance(checksum, str)
        self._checksum = checksum

    @property
    def checksum(self):
        return self._checksum

    @property
    def buffer(self):
        from ..core.protocol.get_buffer import get_buffer
        checksum = self._checksum
        if checksum is None:
            return None
        checksum = bytes.fromhex(checksum)
        buffer_cache = self._manager.cachemanager.buffer_cache
        return get_buffer(checksum, buffer_cache)

    @property
    def value(self):        
        from ..core.protocol.deserialize import deserialize_sync
        from ..core.protocol.expression import get_subpath_sync
        checksum = self._checksum
        celltype = self._celltype
        buffer = self.buffer
        if buffer is None:
            return None        

        celltype = self._celltype
        if celltype == "mixed":
            value = deserialize_sync(buffer, checksum, "mixed", copy=True)
            hash_pattern = self._node.get("hash_pattern")
            if hash_pattern is None:
                return value
            return get_subpath_sync(value, hash_pattern, None)
        elif celltype == "code":
            language = self._node["language"]
            if language in ("python", "ipython"):
                ct = language
            else:
                ct = "text"
        else:
            ct = celltype
        value = deserialize_sync(buffer, checksum, ct, copy=True)
        return value

    def cell(self):
        celltype = self._celltype
        if celltype == "mixed":
            hash_pattern = self._node.get("hash_pattern")
            result = cell("mixed", hash_pattern=hash_pattern)
        elif celltype == "code":
            language = self._node["language"]
            if language in ("python", "ipython"):
                result = cell(celltype=language)
            else:
                result = cell(celltype="text")
        else:
            result = cell(celltype=celltype)
        checksum = None
        if self._checksum is not None:
            checksum = bytes.fromhex(self._checksum)
        result._initial_checksum = checksum, True, False
        return result       

class StructuredCellWrapper(WrapperBase):
    def __init__(self, manager, node):
        assert node["type"] == "cell"
        assert node["celltype"] == "structured"
        super().__init__(manager, node)
    
    @property
    def auth(self):
        checksum = self._node.get("checksum", {}).get("auth")
        return SimpleCellWrapper(self._manager, {}, "mixed", checksum)

    @property
    def buffer(self):
        checksum = self._node.get("checksum", {}).get("buffer")
        return SimpleCellWrapper(self._manager, {}, "mixed", checksum)

    @property
    def schema(self):
        checksum = self._node.get("checksum", {}).get("schema")
        return SimpleCellWrapper(self._manager, {}, "plain", checksum)

    @property
    def value(self):
        checksum = self._node.get("checksum", {}).get("value")
        vcell = SimpleCellWrapper(self._manager, {}, "mixed", checksum)
        return vcell.value

class TransformerWrapper(WrapperBase):
    def __init__(self, manager, node):
        assert node["type"] == "transformer"
        super().__init__(manager, node)
    
    @property
    def code(self):
        checksum = self._node.get("checksum", {}).get("code")
        lang = self._node["language"]
        celltype = lang if lang in ("python", "ipython") else "text"            
        return SimpleCellWrapper(self._manager, {}, celltype, checksum)

    def __getattr__(self, attr):
        node = self._node
        if attr == node["INPUT"]:
            return self._inp()
        elif attr == node["RESULT"]:
            return self._result()
        else:
            raise AttributeError(attr)

    def __dir__(self):
        node = self._node
        return ("code", node["INPUT"], node["RESULT"])
    
    def _inp(self):
        mapping = {
            "input": "value",
            "input_auth": "auth",
            "input_buffer": "buffer",
            "schema": "schema"
        }
        checksums = self._node.get("checksum", {})
        cs = {}
        for k, v in mapping.items():
            if k in checksums:
                cs[v] = checksums[k]
        return StructuredCellWrapper(
            self._manager, 
            {"checksum": cs, "type": "cell", "celltype": "structured"}
        )

    def _result(self):
        mapping = {
            "result": "value",
            "result_buffer": "buffer",
            "result_schema": "schema"
        }
        checksums = self._node.get("checksum", {})
        cs = {}
        for k, v in mapping.items():
            if k in checksums:
                cs[v] = checksums[k]
        return StructuredCellWrapper(
            self._manager, 
            {"checksum": cs, "type": "cell", "celltype": "structured"}
        )

from ..core.manager.tasks import GetBufferTask, DeserializeBufferTask
from ..core.protocol.deserialize import deserialize_cache


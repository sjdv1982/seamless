from zipfile import ZipFile
from io import BytesIO

from seamless import Checksum
from ..core import context, cell
from .. import copying
from copy import deepcopy
from ..highlevel.HelpMixin import HelpMixin

class StaticContext(HelpMixin):
    _parent_path = None

    @classmethod
    def from_graph(cls, graph, *, manager=None):
        from .graph_convert import graph_convert
        graph = graph_convert(graph, None)
        nodes0 = graph["nodes"]
        nodes = {tuple(node["path"]):node for node in nodes0}
        connections = graph["connections"]
        params = graph.get("params", {})
        lib = graph.get("lib", {})
        return cls(nodes, connections, lib, params, manager=manager)

    def __init__(self, nodes, connections, lib={}, params={}, *, manager=None):
        from seamless.workflow.core.manager import Manager
        self._nodes = deepcopy(nodes)
        self._connections = connections
        self._lib = lib
        self._params = params
        self._path = []
        if manager is not None:
            assert isinstance(manager, Manager), type(manager)
            self._manager = manager
        else:
            self._manager = Manager()
        old_root = self._manager.last_ctx()
        self.root = context(toplevel=True,manager=self._manager)
        if old_root is not None:
            self._manager.add_context(old_root)
        for node in self._nodes.values():
            node["path"] = tuple(node["path"])

    def __del__(self):
        self.root.destroy()

    def get_graph(self):
        if self._parent_path is None:
            graph = {}
            graph["nodes"] = deepcopy(list(self._nodes.values()))
            graph["connections"] = deepcopy(self._connections)
            graph["params"] = deepcopy(self._params)
            graph["lib"] = deepcopy(self._lib)
            return graph
        nodes, connections, params  = self._nodes, self._connections, self._params
        path = self._parent_path
        lp = len(path)
        newnodes = []
        for nodepath, node in sorted(nodes.items(), key=lambda kv: kv[0]):
            if len(nodepath) and nodepath[0] == "HELP":
                if len(nodepath[1:]) > lp and nodepath[1:lp+1] == path:
                    newnode = deepcopy(node)
                    newnode["path"] = ("HELP",) + tuple(nodepath[lp+1:])
                    newnodes.append(newnode)
            else:
                if len(nodepath) > lp and nodepath[:lp] == path:
                    newnode = deepcopy(node)
                    newnode["path"] = nodepath[lp:]
                    newnodes.append(newnode)
        new_connections = []
        for connection in connections:
            if connection["type"] == "connection":
                source, target = connection["source"], connection["target"]
                if source[:lp] == path and target[:lp] == path:
                    con = deepcopy(connection)
                    con["source"] = source[lp:]
                    con["target"] = target[lp:]
                    new_connections.append(con)
            elif connection["type"] == "link":
                first, second = connection["first"], connection["second"]
                if first[:lp] == path and second[:lp] == path:
                    con = deepcopy(connection)
                    con["first"] = first[lp:]
                    con["second"] = second[lp:]
                    new_connections.append(con)
        params = deepcopy(params)
        graph = {
            "nodes": newnodes,
            "connections": new_connections,
            "params": params
        }
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


    def get_children(self, type=None, full_path=False):
        if type is not None:
            raise ValueError("StaticContext only supports type=None")
        parent_path = self._parent_path
        result = []
        for path in self._nodes:
            if parent_path is not None:
                pp = path[:len(parent_path)]
                if pp != parent_path:
                    continue
                fullchild = result.append(path[len(parent_path):])
            else:
                fullchild = path
            child = fullchild if full_path else fullchild[0]
            if child not in result and child != "HELP":
                result.append(child)
        return sorted(result)

    @property
    def children(self):
        return self.get_children(type=None)

    @property
    def _children(self):
        full_children = self.get_children(type=None, full_path=True)
        return {path: self._get_child(path) for path in full_children}

    def _get_child(self, path):
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
                if len(p) and p[0] == "HELP":
                    return in_path(p[1:])
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
        elif t == "macro":
            raise NotImplementedError(t)
        else:
            raise TypeError(t)

    @property
    def help(self):
        helpwrapper = super().help
        helpwrapper._wrapped_strongref = self
        return helpwrapper

    def __getattr__(self, attr):
        parent_path = self._parent_path
        if parent_path is None:
            path = (attr,)
        else:
            path = parent_path + (attr,)
        if path not in self._nodes:
            raise AttributeError(attr)
        return self._get_child(path)

class WrapperBase:
    def __init__(self, manager, node):
        self._manager = manager
        self._node = node

class SimpleCellWrapper(WrapperBase):

    def __init__(self, manager, node, celltype, checksum:Checksum):
        super().__init__(manager, node)
        root = self._manager.last_ctx()
        assert root is not None
        self._root = root
        self._celltype = celltype
        checksum = Checksum(checksum)
        self._checksum = checksum

    @property
    def checksum(self):
        return self._checksum

    @property
    def buffer(self):
        from ..core.protocol.get_buffer import get_buffer
        checksum = self._checksum
        if not checksum:
            return None
        return get_buffer(checksum, remote=True,deep=True)

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
            value = deserialize_sync(buffer,  bytes.fromhex(checksum), "mixed", copy=True)
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
        value = deserialize_sync(buffer, bytes.fromhex(checksum), ct, copy=True)
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
        checksum = Checksum(self._checksum)
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
        checksum = self._node.get("checksum", {}).get("buffered")
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
            "input_buffered": "buffered",
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

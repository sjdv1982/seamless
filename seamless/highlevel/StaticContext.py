from ..core import context
from ..core.protocol.calculate_checksum import checksum_cache

class StaticContext:
    _parent_path = None

    @classmethod
    def from_graph(cls, graph, *, manager=None):
        nodes0 = graph["nodes"]
        nodes = {tuple(node["path"]):node for node in nodes0}
        connections = graph["connections"]
        return cls(nodes, connections, manager=manager)

    def __init__(self, nodes, connections, *, manager=None):
        from seamless.core.manager import Manager
        self._nodes = nodes
        self._connections = connections
        if manager is not None:            
            assert isinstance(manager, Manager), type(manager)
            self._manager = manager
        else:
            self._manager = Manager()    
    
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
                checksum = node.get("checksum")
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
        else:
            raise NotImplementedError(t)

class WrapperBase:
    def __init__(self, manager, node):
        self._manager = manager
        self._node = node

class SimpleCellWrapper(WrapperBase):

    def __init__(self, manager, node, celltype, checksum):
        super().__init__(manager, node)
        self._celltype = celltype
        self._checksum = checksum        

    @property
    def checksum(self):
        return self._checksum

    @property
    def buffer(self):
        checksum = self._checksum
        if checksum is None:
            return None
        checksum = bytes.fromhex(checksum)
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
            return buffer
        return GetBufferTask(self._manager, checksum).launch_and_await()

    def _get_value(self, copy):
        celltype = self._celltype
        checksum = self._checksum
        if checksum is not None:
            checksum = bytes.fromhex(checksum)
        if not copy:
            cached_value = deserialize_cache.get((checksum, celltype))
            if cached_value is not None:
                return cached_value
        buffer = self.buffer
        task = DeserializeBufferTask(
            self._manager, buffer, checksum, celltype, 
            copy=copy
        )
        value = task.launch_and_await()
        return value

    @property
    def value(self):
        return self._get_value(copy=True)

    @property
    def data(self):
        return self._get_value(copy=False)

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
        return SimpleCellWrapper(self._manager, {}, "mixed", checksum)

from ..core.manager.tasks import GetBufferTask, DeserializeBufferTask
from ..core.protocol.deserialize import deserialize_cache
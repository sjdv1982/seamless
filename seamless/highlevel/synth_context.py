import weakref

class SynthContext:
    """Context synthesized by a Library or Macro constructor"""
    _context = None
    def __init__(self, parent, path, context=None):
        self._parent = weakref.ref(parent)
        self._path = path
        if context is not None:
            self._context = weakref.ref(context)

    @property
    def status(self):
        result = {}
        for childname in self.get_children():
            child = getattr(self, childname)
            status = child.status
            if status == "Status: OK":
                continue
            result[childname] = child.status
        if len(result):
            return result
        return "Status: OK"

    def __dir__(self):
        return self.get_children()

    def get_children(self, type=None):
        if type is not None:
            raise ValueError("SynthContext only supports type=None")
        path = self._path
        lp = len(path)
        parent = self._parent()
        if parent._runtime_graph is None:
            return []
        dirs = set()
        for npath in parent._runtime_graph.nodes:
            if len(npath) > lp and npath[:lp] == path:
                dirs.add(npath[lp])
        return sorted(list(dirs))

    @property
    def children(self):
        return self.get_children(type=None)

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        return self._get_child(attr)

    def __getitem__(self, item):
        if isinstance(item, (str, int)):
            return self._get_child(item)

    def _get_child(self, attr):
        path = self._path + (attr,)
        parent = self._parent()
        try:
            node = parent._runtime_graph.nodes[path]
        except KeyError:
            if attr in self.__dir__():
                return SynthContext(parent, path)
            raise AttributeError(attr) from None
        if node["type"] == "cell":
            result = Cell()
        elif node["type"] == "transformer":
            result = Transformer()
        elif node["type"] == "macro":
            result = Macro()
        elif node["type"] == "context":
            return SynthContext(parent, path)
        else:
            raise NotImplementedError(node["type"])
        Base.__init__(result, parent, path)
        return result

    def __str__(self):
        if self._path is None:
            path = "<None>"
        path = "." + ".".join(self._path)
        return "Seamless SynthContext: " + path

from .Base import Base
from .Cell import Cell
from .Transformer import Transformer
from .Macro import Macro

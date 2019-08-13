"""
Sets up bidirectional links
Must be between:
    Structured cell and structured cell (implemented as EditChannel)
    Structured cell and simple cell (implemented as EditChannel) or vice versaSimple cell and simple cell (implemented as core.link)
StructuredCell can also be Proxy
"""

raise NotImplementedError

from .Base import Base

def is_simple(arg):
    ###if isinstance(arg, CodeProxy): #too difficult to implement; out-of-order translation of transformers => is_simple = False
    ###    return True
    if isinstance(arg, Proxy):
        return False
    elif isinstance(arg, SubCell):
        return False
    elif isinstance(arg, Cell):
        node = arg._get_hcell()
        if node["celltype"] == "structured":
            return False
        else:
            return True
    else:
        return TypeError(type(arg))

class Link(Base):
    _mynode = None
    def __init__(self, first, second):
        is_simple_first = is_simple(first)
        assert first.authoritative

        is_simple_second = is_simple(second)
        assert second.authoritative
        first_path = first._virtual_path if isinstance(first, Proxy) else first._path
        second_path = second._virtual_path if isinstance(second, Proxy) else second._path
        self._mynode = {
            "type": "link",
            "first": {
                "path": first_path,
                "simple": is_simple_first,
            },
            "second": {
                "path": second_path,
                "simple": is_simple_second,
            },
        }

    @property
    def _node(self):
        parent = self._parent()
        if parent is None:
            return self._mynode
        else:
            return parent._graph.nodes[self._path]

    def _init(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self
        parent._graph.nodes[path] = self._mynode
        del self._mynode

from .proxy import Proxy, CodeProxy
from .Cell import Cell
from .SubCell import SubCell

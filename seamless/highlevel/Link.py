def is_simple(arg):
    if isinstance(arg, Cell):
        node = arg._get_hcell()
        if node["celltype"] == "structured":
            return False
        else:
            return True
    elif isinstance(arg, SubCell):
        return False
    elif isinstance(arg, Proxy): # too difficult, at least for now
        return False
    else:
        return TypeError(type(arg))

class Link:
    """Bidirectional link between two cells"""
    def __init__(self, parent, *, node=None, first=None, second=None):
        self.parent = parent
        if node is None:
            assert first is not None and second is not None
            assert is_simple(first)
            if not isinstance(first, SchemaWrapper):
                assert first.authoritative

            assert is_simple(second)
            if not isinstance(second, SchemaWrapper):
                assert second.authoritative
            vclasses = (Proxy, SchemaWrapper)
            first_path = first._virtual_path if isinstance(first, vclasses) else first._path
            second_path = second._virtual_path if isinstance(second, vclasses) else second._path
            self._node = {
                "type": "link",
                "first": first_path,
                "second": second_path
            }
        else:
            self._node = node
    def remove(self):
        if self._node is None:
            return
        self.parent._graph.connections.remove(self._node)

from .proxy import Proxy, CodeProxy
from .Cell import Cell
from .SubCell import SubCell
from .SchemaWrapper import SchemaWrapper
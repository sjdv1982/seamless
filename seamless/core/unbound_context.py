import weakref

from . import SeamlessBase
from .macro_mode import curr_macro

print("""TODO: 
- Implement "originating macro" (in macro_mode)
- when making a connection, check that for both source and target:
   curr_macro is None or "originating macro" is a subpath of curr_macro
- when making a connection, check that for either source or target:
   "originating macro" is the same as curr_macro

""")
class UnboundManager:
    def __init__(self, ctx):
        self._ctx = weakref.ref(ctx)

    def register_cell(self, cell):
        print("UnboundManager REGISTER CELL", cell)

    def register_transformer(self, transformer):
        print("UnboundManager REGISTER TRANSFORMER", transformer)

    def register_reactor(self, reactor):
        print("UnboundManager REGISTER reactor", reactor)

    def register_macro(self, macro):
        print("UnboundManager REGISTER macro", macro)

    def set_cell(self, cell, value, *, from_buffer):
        print("UnboundManager SET CELL", cell, value, from_buffer)

    def connect_cell(self, cell, other):
        print("UnboundManager CONNECT CELL", cell, other)

    def set_cell_checksum(self, cell, checksum):
        print("UnboundManager SET CELL CHECKSUM", cell, checksum)

    def set_cell_label(self, cell, label):
        print("UnboundManager SET CELL LABEL", label)

    def cell_from_pin(self, pin):
        raise NotImplementedError ### cache branch

    def connect_pin(self, pin, cell):
        print("UnboundManager CONNECT PIN", pin, cell)

class UnboundContext(SeamlessBase):

    _name = None
    _children = {}
    _manager = None    
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"
    _mount = None
    _unmounted = False
    _direct_mode = False

    def __init__(
        self, *,
        name=None,
        context=None
    ):
        self._manager = UnboundManager(self)

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._children and self._children[attr] is not value:
            raise AttributeError(
             "Cannot assign to child '%s'" % attr)
        self._add_child(attr, value)

    def __getattr__(self, attr):
        if attr in self._children:
            return self._children[attr]
        raise AttributeError(attr)

    def _add_child(self, childname, child):
        assert isinstance(child, (UnboundContext, Worker, Cell, Link, StructuredCell))
        if isinstance(child, UnboundContext):
            assert child._context() is self
            self._children[childname] = child
        else:
            self._children[childname] = child
            child._set_context(self, childname)

    def _get_manager(self):
        return self._manager


class Path:
    def __init__(self, obj):
        path = obj.path
        raise NotImplementedError ###cache branch

def path(obj):
    return Path(obj)

from .link import Link
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .structured_cell import StructuredCell

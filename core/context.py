"""Module for Context class."""
from weakref import WeakValueDictionary
from .cell import Cell, CellLike, ExportedCell
from .process import Managed, Process, ProcessLike, InputPinBase, \
  ExportedInputPin, OutputPinBase, ExportedOutputPin, EditorOutputPin
from contextlib import contextmanager as _pystdlib_contextmanager
_active_context = None

def set_active_context(ctx):
    global _active_context
    assert ctx is None or isinstance(ctx, Context)
    _active_context = ctx

def get_active_context():
    return _active_context

@_pystdlib_contextmanager
def active_context_as(ctx):
    previous_context = get_active_context()
    try:
        set_active_context(ctx)
        yield
    finally:
        set_active_context(previous_context)

class Context(CellLike, ProcessLike):
    """Context class. Organizes your cells and processes hierarchically.
    """

    _name = None
    _parent = None
    _registrar = None
    _like_cell = False          #can be set to True by export
    _like_process = False       #can be set to True by export
    _parent = None
    _children = None
    _childids = None
    _manager = None
    registrar = None
    _pins = None

    def __init__(
        self,
        name=None,
        parent=None,
        active_context=True,
    ):
        """Construct a new context.

        Args:
            parent (optional): parent context
            active_context (default: True): Sets the newly constructed context
                as the active context. Subcontexts constructed by macros are
                automatically parented to the active context
        """
        n = name
        if parent is not None and parent._name is not None:
            n = parent._name + "." + str(n)
        self._name = name
        self._parent = parent
        self._pins = {}
        self._children = {}
        self._childids = WeakValueDictionary()
        if parent is not None:
            self._manager = parent._manager
        else:
            from .process import Manager
            self._manager = Manager()
        if active_context:
            set_active_context(self)
        from .registrar import RegistrarAccessor
        self.registrar = RegistrarAccessor(self)

    _dir = ["export", "registrar"]

    def __dir__(self):
        return list(self._subcontexts.keys()) + list(self._children.keys()) \
         + self._dir

    def _add_child(self, childname, child):
        self._children[childname] = child
        self._childids[id(child)] = child
        child._set_context(self)

    def _newcell(self, dtype, naming_pattern="cell"):
        from .cell import cell
        count = 0
        while 1:
            count += 1
            childname = naming_pattern + str(count)
            if not self._hasattr(childname):
                break
        child = cell(dtype)
        self._add_child(childname, child)
        return child

    def __setattr__(self, attr, value):
        if hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._pins:
            raise AttributeError(
             "Cannot assign to pin ''%s'" % attr)
        if attr in self._children:
            self._children[attr].destroy()

        assert isinstance(value, (Managed, CellLike, ProcessLike))
        self._add_child(attr, value)

    def __getattr__(self, attr):
        if attr in self._pins:
            return self._pins[attr]
        elif attr in self._children:
            return self._children[attr]
        else:
            raise AttributeError(attr)

    def __delattr__(self, attr):
        if attr in self._pins:
            raise AttributeError("Cannot delete pin: '%s'" % attr)
        elif attr not in self._children:
            raise AttributeError(attr)
        child = self._children[attr]
        child.destroy()
        self._children.pop(attr)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._children:
            return True
        if attr in self._pins:
            return True
        return False

    def export(self, child, forced=[]):
        """Exports all unconnected inputs and outputs of a child

        If the child is a cell (or cell-like context):
            - export the child's input as primary input (if unconnected)
            - export the child's output as primary output (if unconnected)
            - export any other pins, if forced
            - sets the context as cell-like
        If the child is a process (or process-like context):
            - export all unconnected input and output pins of the child
            - export any other pins, if forced
            - sets the context as process-like

        Arguments:

        child: a direct or indirect child (grandchild) of the context
        forced: contains a list of pin names that are exported in any case
          (even if not unconnected).
          Use "_input" and "_output" to indicate primary cell input and output

        """
        assert child.context._part_of(self)
        mode = None
        if isinstance(child, CellLike) and child._like_cell:
            mode = "cell"
            pins = ["_input", "_output"]
        elif isinstance(child, ProcessLike) and child._like_process:
            mode = "process"
            pins = child._pins.keys()
        else:
            raise TypeError(child)

        def is_connected(pinname):
            if isinstance(child, CellLike) and child._like_cell:
                child2 = child
                if not isinstance(child, Cell):
                    child2 = child.get_cell()
                if pinname == "_input":
                    return (child2._incoming_connections > 0)
                elif pinname == "_output":
                    return (child2._outgoing_connections > 0)
                else:
                    raise ValueError(pinname)
            else:
                pin = child._pins[pinname]
                if isinstance(pin, InputPinBase):
                    manager = pin._get_manager()
                    con_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
                    return (len(con_cells) > 0)
                elif isinstance(pin, OutputPinBase):
                    pin = pin.get_pin()
                    if isinstance(pin, EditorOutputPin):
                        return (len(pin.solid._cell_ids) > 0) or \
                         (len(pin.liquid._cell_ids) > 0)
                    else:
                        return (len(pin._cell_ids) > 0)
                else:
                    raise TypeError(pin)
        pins = [p for p in pins if not is_connected(p)] + forced
        if not len(pins):
            raise Exception("Zero pins to be exported!")
        for pinname in pins:
            if self._hasattr(pinname):
                raise Exception("Cannot export pin '%s', context has already this attribute" % pinname)
            if isinstance(child, CellLike) and child._like_cell:
                if not isinstance(child, Cell):
                    child = child.get_cell()
                    self._pins[pinname] = ExportedCell(child)
            else:
                pin = child._pins[pinname]
                if isinstance(pin, InputPinBase):
                    self._pins[pinname] = ExportedInputPin(pin)
                elif isinstance(pin, OutputPinBase):
                    self._pins[pinname] = ExportedOutputPin(pin)

        if mode == "cell":
            self._like_cell = True
        elif mode == "process":
            self._like_process = True

    def _part_of(self, ctx):
        assert isinstance(ctx, Context)
        if ctx is self:
            return True
        elif self._parent is None:
            return False
        else:
            return self._parent._part_of(ctx)

    def _root(self):
        if self._parent is None:
            return self
        else:
            return self._parent._root()

    def _set_context(self, ctx):
        #TODO: detach if already in a context
        self._parent = ctx

    def destroy(self):
        for childname in self._children:
            child = self._children[name]
            child.destroy()

def context(**kwargs):
    """Return a new Context object."""
    ctx = Context(**kwargs)
    return ctx

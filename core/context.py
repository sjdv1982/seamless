"""Module for Context class."""
from weakref import WeakValueDictionary
from . import SeamlessBase
from .cell import Cell, CellLike, ExportedCell
from .process import Managed, Process, ProcessLike, InputPinBase, \
  ExportedInputPin, OutputPinBase, ExportedOutputPin, EditorOutputPin
from contextlib import contextmanager as _pystdlib_contextmanager
_active_context = None

#TODO: subcontexts inherit manager from parent? see process.connect source code

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

class Context(SeamlessBase, CellLike, ProcessLike):
    """Context class. Organizes your cells and processes hierarchically.
    """

    _name = None
    _registrar = None
    _like_cell = False          #can be set to True by export
    _like_process = False       #can be set to True by export
    _children = None
    _childids = None
    _manager = None
    registrar = None
    _pins = None
    _auto = None

    def __init__(
        self,
        name=None,
        context=None,
        active_context=True,
    ):
        """Construct a new context.

        Args:
            context (optional): parent context
            active_context (default: True): Sets the newly constructed context
                as the active context. Subcontexts constructed by macros are
                automatically parented to the active context
        """
        n = name
        if context is not None and context._name is not None:
            n = context._name + "." + str(n)
        self._name = name
        self._pins = {}
        self._children = {}
        self._childids = WeakValueDictionary()
        self._auto = set() #TODO: save this also when serializing
        if context is not None:
            self._manager = context._manager
        else:
            from .process import Manager
            self._manager = Manager()
        if active_context:
            set_active_context(self)
        from .registrar import RegistrarAccessor
        self.registrar = RegistrarAccessor(self)

    _dir = ["_name", "export", "registrar", "cells"]

    @property
    def cells(self):
        from .cell import CellLike
        return [v for k,v in self._children.items() if isinstance(v, CellLike) and v._like_cell]

    def __dir__(self):
        return [c for c in self._children.keys() if c not in self._auto] \
         + [c for c in self._pins.keys()] + self._dir

    def _add_child(self, childname, child):
        self._children[childname] = child
        self._childids[id(child)] = child
        child._set_context(self)

    def _add_new_cell(self, cell, naming_pattern="cell"):
        from .cell import Cell
        assert isinstance(cell, Cell)
        count = 0
        while 1:
            count += 1
            cell_name = naming_pattern + str(count)
            if not self._hasattr(cell_name):
                break
        self._auto.add(cell_name)
        self._add_child(cell_name, cell)
        return cell

    def _add_new_process(self, process, naming_pattern="process"):
        from .process import Process
        assert isinstance(process, Process)
        count = 0
        while 1:
            count += 1
            process_name = naming_pattern + str(count)
            if not self._hasattr(process_name):
                break
        self._auto.add(process_name)
        self._add_child(process_name, process)
        return process

    def _new_subcontext(self, naming_pattern="ctx"):
        count = 0
        while 1:
            count += 1
            context_name = naming_pattern + str(count)
            if not self._hasattr(context_name):
                break
        ctx = context(context=self, active_context=False)
        self._auto.add(context_name)
        self._add_child(context_name, ctx)
        return ctx

    def __setattr__(self, attr, value):
        if hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._pins:
            raise AttributeError(
             "Cannot assign to pin ''%s'" % attr)
        if attr in self._children and self._children[attr] is not value:
            self._children[attr].destroy()

        assert isinstance(value, (Managed, CellLike, ProcessLike)), type(value)
        value._set_context(self, force_detach=True)
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
        elif self._context is None:
            return False
        else:
            return self._context._part_of(ctx)

    def _root(self):
        if self._context is None:
            return self
        else:
            return self._context._root()

    def _set_context(self, ctx, force_detach=True):
        if self._context is not None:
            if self._context is not ctx or force_detach:
                for childname, child in self._context._children.items():
                    if child is self:
                        self._context._children.pop(childname)
                        break
                else:
                    print("WARNING, orphaned context child?")
        self._context = ctx

    def destroy(self):
        if self._destroyed:
            return
        #print("CONTEXT DESTROY")
        for childname in list(self._children):
            child = self._children[childname]
            child.destroy()
        super().destroy()

def context(**kwargs):
    """Return a new Context object."""
    ctx = Context(**kwargs)
    return ctx

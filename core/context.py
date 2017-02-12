"""Module for Context class."""
from weakref import WeakValueDictionary
from . import SeamlessBase
from .cell import Cell, CellLike
from .process import Managed, Process, ProcessLike,  \
  InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin, \
  EditPinBase, ExportedEditPin
from contextlib import contextmanager as _pystdlib_contextmanager
_active_context = None
_active_owner = None

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


def set_active_owner(parent):
    global _active_owner
    assert parent is None or isinstance(parent, SeamlessBase)
    _active_owner = parent

def get_active_owner():
    return _active_owner

@_pystdlib_contextmanager
def active_owner_as(parent):
    previous_parent = get_active_owner()
    try:
        set_active_owner(parent)
        yield
    finally:
        set_active_owner(previous_parent)

class Context(SeamlessBase, CellLike, ProcessLike):
    """Context class. Organizes your cells and processes hierarchically.
    """

    _name = None
    _like_cell = False          #can be set to True by export
    _like_process = False       #can be set to True by export
    _children = {}
    _manager = None
    registrar = None
    _pins = []
    _auto = None
    _owned = []
    _owner = None

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
                as the active context. New seamless objects are automatically
                parented to the active context
        """
        super().__init__()
        n = name
        if context is not None and context._name is not None:
            n = context._name + "." + str(n)
        self._name = name
        self._pins = {}
        self._children = {}
        self._auto = set()
        if context is not None:
            self._manager = context._manager
        else:
            from .manager import Manager
            self._manager = Manager()
        if active_context:
            set_active_context(self)
        from .registrar import RegistrarAccessor
        self.registrar = RegistrarAccessor(self)

    _dir = ["_name", "export", "registrar", "cells", "tofile"]

    @property
    def cells(self):
        from .cell import CellLike
        return [v for k,v in self._children.items() if isinstance(v, CellLike) and v._like_cell]

    def __dir__(self):
        return [c for c in self._children.keys() if c not in self._auto] \
         + [c for c in self._pins.keys()] + self._dir

    def _macro_check(self, child, child_macro_control):
        from .macro import get_macro_mode
        if not get_macro_mode():
            macro_control = self._macro_control()
        if not get_macro_mode() and \
         macro_control is not None and macro_control is not child_macro_control:
            macro_cells = macro_control._macro_object.cell_args.values()
            macro_cells = sorted([str(c) for c in macro_cells])
            macro_cells = "\n  " + "\n  ".join(macro_cells)
            child_path = "." + ".".join(child.path)
            if get_active_owner() is not None:
                child_path += " (active owner: {0})".format(get_active_owner())
            if macro_control is self:
                print("""***********************************************************************************************************************
WARNING: {0} is now a child of {1}, which is under live macro control.
The macro is controlled by the following cells: {2}
When any of these cells change and the macro is re-executed, the child object will be deleted and likely not re-created
***********************************************************************************************************************"""\
                .format(child_path, self, macro_cells))
            elif macro_control is not None:
                print("""***********************************************************************************************************************
WARNING: {0} is now a child of {1}, which is a child of, or owned by, {2}, which is under live macro control.
The macro is controlled by the following cells: {3}
When any of these cells change and the macro is re-executed, the child object will be deleted and likely not re-created
***********************************************************************************************************************"""\
                .format(child_path, self, macro_control, macro_cells))

    def _add_child(self, childname, child, force_detach=False):
        from .macro import get_macro_mode
        if not get_macro_mode():
            child_macro_control = child._macro_control()
        child._set_context(self, childname, force_detach)
        from .registrar import RegistrarObject
        self._children[childname] = child
        self._manager._childids[id(child)] = child
        if not get_macro_mode():
            self._macro_check(child, child_macro_control)


    def _add_new_cell(self, cell, naming_pattern="cell"):
        from .cell import Cell
        assert isinstance(cell, Cell)
        assert cell._context is None
        count = 0
        while 1:
            count += 1
            cell_name = naming_pattern + str(count)
            if not self._hasattr(cell_name):
                break
        self._auto.add(cell_name)
        self._add_child(cell_name, cell)
        return cell_name

    def _add_new_process(self, process, naming_pattern="process"):
        from .process import Process
        assert isinstance(process, Process)
        assert process._context is None
        count = 0
        while 1:
            count += 1
            process_name = naming_pattern + str(count)
            if not self._hasattr(process_name):
                break
        self._auto.add(process_name)
        self._add_child(process_name, process)
        return process_name

    def _add_new_registrar_object(self, robj, naming_pattern="registrar_object"):
        from .registrar import RegistrarObject
        assert isinstance(robj, RegistrarObject)
        assert robj._context is None
        count = 0
        while 1:
            count += 1
            robj_name = naming_pattern + str(count)
            if not self._hasattr(robj_name):
                break
        self._auto.add(robj_name)
        self._add_child(robj_name, robj)
        return robj_name

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
        self._add_child(attr, value, force_detach=True)

    def __getattr__(self, attr):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return getattr(successor, attr)
            else:
                raise AttributeError("Context has been destroyed, cannot find successor")

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
                if isinstance(pin, (InputPinBase, EditPinBase)):
                    manager = pin._get_manager()
                    con_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
                    return (len(con_cells) > 0)
                elif isinstance(pin, OutputPinBase):
                    pin = pin.get_pin()
                    return (len(pin._cell_ids) > 0)
                else:
                    raise TypeError(pin)
        pins = [p for p in pins if not is_connected(p)] + forced
        if not len(pins):
            raise Exception("Zero pins to be exported!")
        for pinname in pins:
            if self._hasattr(pinname):
                raise Exception("Cannot export pin '%s', context has already this attribute" % pinname)
            pin = child._pins[pinname]
            if isinstance(pin, InputPinBase):
                self._pins[pinname] = ExportedInputPin(pin)
            elif isinstance(pin, OutputPinBase):
                self._pins[pinname] = ExportedOutputPin(pin)
            elif isinstance(pin, EditPinBase):
                self._pins[pinname] = ExportedEditPin(pin)
            else:
                raise TypeError(pin)

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

    def _owns_all(self):
        owns = super()._owns_all()
        for child in self._children.values():
            owns.add(child)
            owns.update(child._owns_all())
        return owns

    def tofile(self, filename, backup=True):
        from .tofile import tofile
        tofile(self, filename, backup)

    @classmethod
    def fromfile(cls, filename):
        from .io import fromfile
        return fromfile(cls, filename)

    def destroy(self):
        if self._destroyed:
            return
        #print("CONTEXT DESTROY", self, list(self._children.keys()))
        for childname in list(self._children.keys()):
            if childname not in self._children:
                continue #child was destroyed automatically by another child
            child = self._children[childname]
            child.destroy()
        super().destroy()

    def _validate_path(self, required_path=None):
        required_path = super()._validate_path(required_path)
        for childname, child in self._children.items():
            child._validate_path(required_path + (childname,))
        return required_path

    def _cleanup_auto(self):
        #TODO: test better, or delete? disable for now
        return ###
        manager = self._manager
        for a in sorted(list(self._auto)):
            if a not in self._children:
                self._auto.remove(a)
                continue
            cell = self._children[a]
            if not isinstance(cell, Cell):
                continue
            #if cell.data is not None:
            #    continue

            cell_id = manager.get_cell_id(cell)
            incons = manager.cell_to_output_pin.get(cell, [])
            if len(incons):
                continue
            if cell_id in manager.listeners:
                outcons = manager.listeners[cell_id]
                if len(outcons):
                    continue
            macro_listeners = manager.macro_listeners.get(cell_id, [])
            if len(macro_listeners):
                continue
            child = self._children.pop(a)
            child.destroy()
            print("CLEANUP", self, a)
            self._auto.remove(a)



def context(**kwargs):
    """Return a new Context object."""
    ctx = Context(**kwargs)
    return ctx

"""Module for Context class."""
from weakref import WeakValueDictionary
from collections import OrderedDict
from . import SeamlessBase, Managed
from .cell import Cell, CellLike
from .worker import Worker, WorkerLike,  \
  InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin, \
  EditPinBase, ExportedEditPin
from contextlib import contextmanager as _pystdlib_contextmanager
_active_context = None
_active_owner = None

#TODO: subcontexts inherit manager from parent? see worker.connect source code

class PrintableList(list):
    def __str__(self):
        return str([v.format_path() for v in self])

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

class Wrapper:
    def __init__(self, wrapped):
        self._wrapped = wrapped
    def __getattr__(self, attr):
        if attr not in self._wrapped:
            raise AttributeError(attr)
        return self._wrapped[attr]
    def __getitem__(self, attr):
        return self.__getattr__(attr)
    def __iter__(self):
        return iter(self._wrapped.keys())
    def __dir__(self):
        return self._wrapped.keys()
    def __str__(self):
        return str(sorted(list(self._wrapped.keys())))
    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

class Context(SeamlessBase, CellLike, WorkerLike):
    """Context class. Organizes your cells and workers hierarchically.
    """

    _name = None
    _like_cell = False
    _like_worker = False       #can be set to True by export
    _children = {}
    _manager = None
    registrar = None
    _pins = []
    _auto = None
    _owned = []
    _owner = None
    _exported_child = None

    def __init__(
        self,
        name=None,
        context=None,
        active_context=True,
    ):
        """Construct a new context.

A context can contain cells, workers (= transformers and reactors),
and other contexts.

**Important methods and attributes**:
    ``.tofile()``, ``.fromfile()``, ``.equilibrate()``, ``.status()``

In addition, the ``.registrar`` attribute contains the registrars.

For cells with the correct `dtype`, use ``registrar.register(cell)``
to register them.
As of seamless 0.1, there are two global registrars:

  - The Python registrar: for pythoncells.

    Simply registers all Python objects in the Python code's globals.

    Use ``registrar.python.connect(name_of_python_object, worker)`` to use the
    data model in a worker.

    See examples/test-python-registrar.py for an example.

  - The silk registrar: for cells with dtype ("text", "code", "silk")

    This registers all Silk data models in the cell.

    Use ``registrar.silk.connect(name_of_datamodel, worker)`` to use
    the data model in a worker.

    As of seamless 0.1, Silk is not yet documented: see examples/test-macro.py
    or examples/fireworks/fireworks.py for examples on how to work with Silk
    data models.

Parameters
----------
context : context or None
    parent context
active_context: bool (default = True)
    Sets the newly constructed context as the active context (default is True).
    New seamless objects are automatically parented to the active context.

"""
        super().__init__()
        n = name
        if context is not None and context._name is not None:
            n = context._name + "." + n.format_path()
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

    def __str__(self):
        p = self.format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _get_manager(self):
        return self._manager

    def _shell(self, toplevel=True):
        if self._exported_child is None:
            raise AttributeError("""Context %s: no exported child has been set.
You can only invoke shell() directly on one of its children""" % self.format_path())
        child = self._exported_child._find_successor()
        if child._destroyed:
            raise AttributeError("""Context %s: exported child has been destroyed.
You can only invoke shell() directly on one of its remaining children""" % self.format_path())
        namespace, title = child._shell(toplevel=False)
        if toplevel:
            name = self.format_path()
            if name == ".":
                name = "<toplevel>"
            title += " in context %s" % name
        return namespace, title

    def __dir__(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.__dir__()
        return self.METHODS + dir(self.PINS) + dir(self.CHILDREN)

    @property
    def METHODS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.METHODS
        result = [k for k in super().__dir__() \
            if not k.startswith("_")]
        for name in ["fromfile", "export", "context"]:
            result.remove(name)
        return sorted(result)

    @property
    def PINS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.PINS
        return Wrapper(self._pins)

    @property
    def CHILDREN(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.CHILDREN
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if k not in self._auto}
        )

    @property
    def ALL_CHILDREN(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.ALL_CHILDREN
        return Wrapper(self._children)

    @property
    def CELLS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.CELLS
        from .cell import CellLike
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if isinstance(v, CellLike) and v._like_cell\
             and not k in self._auto}
        )

    @property
    def AUTO_CELLS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.AUTO_CELLS
        from .cell import CellLike
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if isinstance(v, CellLike) and v._like_cell\
             and k in self._auto}
        )

    @property
    def WORKERS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.WORKERS
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if isinstance(v, WorkerLike) and v._like_worker}
        )

    @property
    def CONTEXTS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.CONTEXTS
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if isinstance(v, Context) and \
             not v._like_worker and not v._like_cell}
        )

    @property
    def ALL_CONTEXTS(self):
        if self._destroyed:
            successor = self._find_successor()
            if successor:
                return successor.ALL_CONTEXTS
        return Wrapper(
            {k:v for k,v in self._children.items() \
             if isinstance(v, Context)}
        )

    @property
    def tree(self):
        result = OrderedDict()
        for childname in sorted(list(self._children.keys())):
            child = self._children[childname]
            value = child
            if isinstance(child, Context):
                value = child.tree
            result[childname] = value
        return result

    def _macro_check(self, child, child_macro_control):
        from .macro import get_macro_mode
        if not get_macro_mode():
            macro_control = self._macro_control()
        if not get_macro_mode() and \
         macro_control is not None and macro_control is not child_macro_control:
            macro_cells = macro_control._macro_object.cell_args.values()
            macro_cells = sorted([c.format_path() for c in macro_cells])
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

    def _set_context(self, context, name, force_detach=False):
        super()._set_context(context, name, force_detach)
        if self._manager is not context._manager:
            assert not len(self._children) #TODO: insert a non-empty context into a parent context
            self._manager = context._manager

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

    def _add_new_worker(self, worker, naming_pattern="worker"):
        from .worker import Worker
        assert isinstance(worker, Worker)
        assert worker._context is None
        count = 0
        while 1:
            count += 1
            worker_name = naming_pattern + str(count)
            if not self._hasattr(worker_name):
                break
        self._auto.add(worker_name)
        self._add_child(worker_name, worker)
        return worker_name

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
        from .worker import ExportedInputPin, ExportedOutputPin, \
          ExportedEditPin
        if hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._pins:
            raise AttributeError(
             "Cannot assign to pin ''%s'" % attr)
        pintypes = (ExportedInputPin, ExportedOutputPin, ExportedEditPin)
        if isinstance(value, pintypes):
            #TODO: check that pin target is a child
            self._pins[attr] = value
            self._pins[attr]._set_context(self, attr)
            return

        assert isinstance(value, (Managed, CellLike, WorkerLike)), type(value)
        if attr in self._children and self._children[attr] is not value:
            self._children[attr].destroy()
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
        self._children.pop(attr, None)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._children:
            return True
        if attr in self._pins:
            return True
        return False

    def export(self, child, forced=[], skipped=[]):
        """Exports all unconnected inputs and outputs of a child

        If the child is a worker (or worker-like context):
            - export the child's inputs/outputs as primary inputs/outputs
                (if unconnected, and not in skipped)
            - export any other pins, if forced
            - sets the context as worker-like
        Outputs with a single, undefined, auto cell are considered unconnected

        Arguments:

        child: a direct or indirect child (grandchild) of the context
        forced: contains a list of pin names that are exported in any case
          (even if not unconnected).
        skipped: contains a list of pin names that are never exported
          (even if unconnected).

        """
        assert child.context._part_of(self)
        if isinstance(child, WorkerLike) and child._like_worker:
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
                    manager = pin._get_manager()
                    if len(pin._cell_ids) == 0:
                        return False
                    elif len(pin._cell_ids) > 1:
                        return True
                    con_cell = manager.cells[pin._cell_ids[0]]
                    if con_cell._data is not None:
                        return True
                    if con_cell.name not in self._auto:
                        return True
                    return False
                else:
                    raise TypeError(pin)
        pins = [p for p in pins if not is_connected(p) and p not in skipped]
        pins = pins + [p for p in forced if p not in pins]
        if not len(pins):
            raise Exception("Zero pins to be exported!")
        for pinname in pins:
            if self._hasattr(pinname):
                raise Exception("Cannot export pin '%s', context has already this attribute" % pinname)
            pin = child._pins[pinname]
            if isinstance(pin, InputPinBase):
                self._pins[pinname] = ExportedInputPin(pin)
                self._pins[pinname]._set_context(self, pinname)
            elif isinstance(pin, OutputPinBase):
                self._pins[pinname] = ExportedOutputPin(pin)
                self._pins[pinname]._set_context(self, pinname)
            elif isinstance(pin, EditPinBase):
                self._pins[pinname] = ExportedEditPin(pin)
                self._pins[pinname]._set_context(self, pinname)
            else:
                raise TypeError(pin)

        self._like_worker = True
        self._exported_child = child

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
        """Saves the context to a file
        Arguments:
            filename: name of the file to save to
            backup (bool, default=True):
              If the file already exists, rename the old file
               to filename + str(N), where N is the lowest number
               possible such that filename + str(N) does not exist
        """
        from .tofile import tofile
        tofile(self, filename, backup)

    @classmethod
    def fromfile(cls, filename):
        """Class method. Loads a context from file
        Arguments:
            filename: name of the file to load
        """
        from .io import fromfile
        return fromfile(cls, filename)

    def destroy(self):
        """
        Destroys a context
        Detaches the context from its parent context, if any
        Destroys all children
        """
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

    def equilibrate(self, timeout=None, report=0.5):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds
        Report the workers that are not stable every "report" seconds
        """
        from .. import run_work
        import time
        start_time = time.time()
        last_report_time = start_time
        run_work()
        manager = self._manager
        last_unstable = []
        #print("UNSTABLE", list(manager.unstable_workers))
        while 1:
            curr_time = time.time()
            if curr_time - last_report_time > report:
                unstable = list(manager.unstable_workers)
                if last_unstable != unstable:
                    last_unstable = unstable
                    print("Waiting for:", self.unstable_workers)
                last_report_time = curr_time
            if timeout is not None:
                if curr_time - start_time > timeout:
                    break
            run_work()
            len1 = len(manager.unstable_workers)
            time.sleep(0.001)
            run_work()
            len2 = len(manager.unstable_workers)
            if len1 == 0 and len2 == 0:
                break
        unstable = list(manager.unstable_workers)
        run_work()
        return unstable
        #print("UNSTABLE", list(manager.unstable_workers))

    @property
    def unstable_workers(self):
        """All unstable workers (not in equilibrium)"""
        result = list(self._manager.unstable_workers)
        return PrintableList(sorted(result, key=lambda p:p.format_path()))

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
            self._auto.remove(a)

    def status(self):
        """The computation status of the context
        Returns a dictionary containing the status of all children that are not OK.
        If all children are OK, returns OK
        """
        from .registrar import RegistrarObject
        result = {}
        for childname, child in self._children.items():
            if childname in self._auto:
                continue
            if isinstance(child, RegistrarObject):
                continue
            s = child.status()
            if s != self.StatusFlags.OK.name:
                result[childname] = s
        if len(result):
            return result
        return self.StatusFlags.OK.name


def context(**kwargs):
    ctx = Context(**kwargs)
    return ctx
context.__doc__ = Context.__init__.__doc__

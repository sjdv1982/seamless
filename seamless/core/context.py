"""Module for Context class."""
from weakref import WeakValueDictionary
from collections import OrderedDict
from . import SeamlessBase
from .manager import Manager
#from .cell import Cell ###
#from .worker import Worker,  \
#  InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin, \
#  EditPinBase, ExportedEditPin ###
from macro import get_macro_mode
from contextlib import contextmanager as _pystdlib_contextmanager
_active_context = None

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

class Context(SeamlessBase):
    """Context class. Organizes your cells and workers hierarchically.
    """

    _name = None
    _children = {}
    _manager = None
    _pins = []
    _auto = None

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
    ``.equilibrate()``, ``.status()``

Parameters
----------
context : context or None
    parent context
active_context: bool (default = True)
    Sets the newly constructed context as the active context (default is True).
    New seamless objects are automatically parented to the active context.

"""
        assert get_macro_mode()
        super().__init__()
        n = name
        if context is not None and context._name is not None:
            n = context._name + "." + n.format_path()
        self._name = name
        self._pins = {}
        self._children = {}
        self._auto = set()
        self._manager = Manager()
        if active_context:
            set_active_context(self)

    def _get_manager(self):
        return self._manager

    def __str__(self):
        p = self.format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _add_child(self, childname, child, force_detach=False):
        from .macro import get_macro_mode
        child._set_context(self, childname, force_detach)
        self._children[childname] = child

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
        assert get_macro_mode()
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._pins:
            raise AttributeError(
             "Cannot assign to pin ''%s'" % attr)
        from .worker import ExportedInputPin, ExportedOutputPin, \
          ExportedEditPin
        pintypes = (ExportedInputPin, ExportedOutputPin, ExportedEditPin)
        if isinstance(value, pintypes):
            #TODO: check that pin target is a child
            self._pins[attr] = value
            self._pins[attr]._set_context(self, attr)
            return

        assert isinstance(value, SeamlessBase), type(value)
        if attr in self._children and self._children[attr] is not value:
            self._children[attr].destroy()
        self._add_child(attr, value, force_detach=True)

    def __getattr__(self, attr):
        if attr in self._pins:
            return self._pins[attr]
        elif attr in self._children:
            return self._children[attr]
        else:
            raise AttributeError(attr)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._children:
            return True
        if attr in self._pins:
            return True
        return False

    def _part_of(self, ctx):
        assert isinstance(ctx, Context)
        if ctx is self:
            return True
        elif self._context is None:
            return False
        else:
            return self._context._part_of(ctx)

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
        assert get_macro_mode()
        assert child.context._part_of(self)
        if isinstance(child, (Worker, Context)):
            pins = child._pins.keys()
        else:
            raise TypeError(child)

        def is_connected(pinname):
            if isinstance(child, Cell):
                if pinname == "_input":
                    return (child._incoming_connections > 0)
                elif pinname == "_output":
                    return (child._outgoing_connections > 0)
                else:
                    raise ValueError(pinname)
            else:
                pin = child._pins[pinname]
                if isinstance(pin, (InputPinBase, EditPinBase)):
                    raise NotImplementedError  ###
                    #manager = pin._get_manager()
                    #con_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
                    #return (len(con_cells) > 0)
                elif isinstance(pin, OutputPinBase):
                    raise NotImplementedError  ###
                    #pin = pin.get_pin()
                    #manager = pin._get_manager()
                    #if len(pin._cell_ids) == 0:
                    #    return False
                    #elif len(pin._cell_ids) > 1:
                    #    return True
                    #con_cell = manager.cells[pin._cell_ids[0]]
                    #if con_cell._data is not None:
                    #    return True
                    #if con_cell.name not in self._auto:
                    #    return True
                    #return False
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

        self._exported_child = child

    def equilibrate(self, timeout=None, report=0.5):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds
        Report the workers that are not stable every "report" seconds
        """
        raise NotImplementedError ###
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

    def status(self):
        """The computation status of the context
        Returns a dictionary containing the status of all children that are not OK.
        If all children are OK, returns OK
        """
        result = {}
        for childname, child in self._children.items():
            if childname in self._auto:
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

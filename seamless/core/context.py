"""Module for Context class."""
from weakref import WeakValueDictionary
from collections import OrderedDict
from . import SeamlessBase
from .mount import MountItem
from .macro import get_macro_mode, macro_register
import time

class Context(SeamlessBase):
    """Context class. Organizes your cells and workers hierarchically.
    """

    _name = None
    _children = {}
    _manager = None
    _pins = []
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"
    _mount = None

    def __init__(
        self, *,
        name=None,
        context=None,
        toplevel=False,
    ):
        """Construct a new context.

A context can contain cells, workers (= transformers and reactors),
and other contexts.

**Important methods and attributes**:
    ``.equilibrate()``, ``.status()``

Parameters
----------
name: str
    name of the context within the parent context
context : context or None
    parent context
"""
        assert get_macro_mode()
        super().__init__()
        if context is not None:
            self._set_context(context, name)
        if toplevel:
            assert context is None
            self._toplevel = True
            self._manager = Manager(self)
        else:
            assert context is not None

        self._pins = {}
        self._children = {}
        self._auto = set()
        macro_register.add(self)

    def _set_context(self, context, name):
        super()._set_context(context, name)
        context_name = context._name
        if context_name is None:
            context_name = ()
        self._name = context_name + (name,)
        self._manager = Manager(self)

    def _get_manager(self):
        assert self._toplevel or self._context is not None  #context must have a parent, or be toplevel
        return self._manager

    def __str__(self):
        p = self.format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _add_child(self, childname, child):
        from .macro import get_macro_mode
        assert get_macro_mode()
        assert isinstance(child, (Context, Worker, CellLikeBase))
        if isinstance(child, Context):
            assert child._context is self
        else:
            child._set_context(self, childname)
        self._children[childname] = child
        self._manager.notify_attach_child(childname, child)

    def _add_new_cell(self, cell):
        assert isinstance(cell, Cell)
        assert cell._context is None
        count = 0
        while 1:
            count += 1
            cell_name = cell._naming_pattern + str(count)
            if not self._hasattr(cell_name):
                break
        self._auto.add(cell_name)
        self._add_child(cell_name, cell)
        return cell_name

    def _add_new_worker(self, worker):
        from .worker import Worker
        assert isinstance(worker, Worker)
        assert worker._context is None
        count = 0
        while 1:
            count += 1
            worker_name = worker._naming_pattern + str(count)
            if not self._hasattr(worker_name):
                break
        self._auto.add(worker_name)
        self._add_child(worker_name, worker)
        return worker_name

    def _add_new_subcontext(self, ctx):
        assert isinstance(ctx, Context)
        count = 0
        while 1:
            count += 1
            context_name = ctx._naming_pattern + str(count)
            if not self._hasattr(context_name):
                break
        self._auto.add(context_name)
        self._add_child(context_name, ctx)
        return ctx

    def __setattr__(self, attr, value):
        assert get_macro_mode()
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._pins:
            raise AttributeError(
             "Cannot assign to pin '%s'" % attr)
        '''
        from .worker import ExportedInputPin, ExportedOutputPin, \
          ExportedEditPin
        pintypes = (ExportedInputPin, ExportedOutputPin, ExportedEditPin)
        if isinstance(value, pintypes):
            #TODO: check that pin target is a child
            self._pins[attr] = value
            self._pins[attr]._set_context(self, attr)
            return
        '''

        if attr in self._children and self._children[attr] is not value:
            raise AttributeError(
             "Cannot assign to child '%s'" % attr)
        self._add_child(attr, value)

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
    '''
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
    '''

    def _flush_workqueue(self):
        manager = self._get_manager()
        manager.workqueue.flush()
        finished = True
        for childname, child in self._children.items():
            if isinstance(child, Context):
                remaining = child.equilibrate(0.001)
                if len(remaining):
                    finished = False
        manager.mountmanager.tick()
        return finished

    def equilibrate(self, timeout=None, report=0.5):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds
        Report the workers that are not stable every "report" seconds
        """
        start_time = time.time()
        last_report_time = start_time
        self._flush_workqueue()
        last_unstable = []
        while 1:
            if self._destroyed:
                return []
            curr_time = time.time()
            if curr_time - last_report_time > report:
                manager = self._get_manager()
                unstable = list(manager.unstable)
                if last_unstable != unstable:
                    last_unstable = unstable
                    print("Waiting for:", self.unstable_workers)
                last_report_time = curr_time
            if timeout is not None:
                if curr_time - start_time > timeout:
                    break
            finished1 = self._flush_workqueue()
            if self._destroyed:
                return []
            manager = self._get_manager()
            len1 = len(manager.unstable)
            time.sleep(0.001)
            finished2 = self._flush_workqueue()
            if self._destroyed:
                return []
            manager = self._get_manager()
            len2 = len(manager.unstable)
            if finished1 and finished2:
                if len1 == 0 and len2 == 0:
                    break
        if self._destroyed:
            return []
        manager = self._get_manager()
        manager.workqueue.flush()
        if self._destroyed:
            return []
        unstable = list(manager.unstable)
        return unstable

    @property
    def unstable_workers(self):
        """All unstable workers (not in equilibrium)"""
        from . import SeamlessBaseList
        result = list(self._manager.unstable)
        return SeamlessBaseList(sorted(result, key=lambda p:p.format_path()))

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

    def mount(self, path, mode="rw", authority="cell"):
        """Performs a "lazy mount"; context is mounted to the directory path when macro mode ends
        math: directory path
        mode: "r", "w" or "rw" (passed on to children)
        authority: "cell", "file" or "file-strict" (passed on to children)
        """
        self._mount = {
            "path": path,
            "mode": mode,
            "authority": authority
        }
        MountItem(None, self,  **self._mount) #to validate parameters

    def __dir__(self):
        result = []
        result[:] = self._methods
        for k in self._children:
            if k not in result:
                result.append(k)
        return result

    @property
    def self(self):
        return _ContextWrapper(self)

Context._methods = [m for m in Context.__dict__ if not m.startswith("_") \
      and m != "StatusFlags"]

def context(**kwargs):
    ctx = Context(**kwargs)
    return ctx
context.__doc__ = Context.__init__.__doc__

print("context: TODO symlinks (can be cells/workers/contexts outside this context)")

class _ContextWrapper:
    _methods = [m for m in Context.__dict__ if not m.startswith("_") \
      and m not in ("self", "StatusFlags")]
    def __init__(self, wrapped):
        super().__setattr__("_wrapped", wrapped)
    def __getattr__(self, attr):
        if attr not in self._methods:
            raise AttributeError(attr)
        return getattr(self._wrapped, attr)
    def __dir__(self):
        return self._methods
    def __setattr__(self, attr, value):
        raise AttributeError("_ContextWrapper is read-only")

from .cell import Cell, CellLikeBase
'''
from .worker import Worker,  \
  InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin, \
  EditPinBase, ExportedEditPin
'''
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase

from .manager import Manager

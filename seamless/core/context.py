"""Module for Context class."""
from weakref import WeakValueDictionary
from collections import OrderedDict
from . import SeamlessBase
from .mount import MountItem, is_dummy_mount
from . import get_macro_mode, macro_register
from .macro_mode import toplevel_register, macro_mode_on, with_macro_mode
import time
from contextlib import contextmanager

@contextmanager
def null_context():
    yield

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
    _unmounted = False
    _seal = None
    _direct_mode = False
    _exported = True

    def __init__(
        self, *,
        name=None,
        context=None,
        toplevel=False
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
        if get_macro_mode():
            direct_mode = False
            macro_mode_context = null_context
        else:
            direct_mode = True
            macro_mode_context = macro_mode_on
        with macro_mode_context():
            super().__init__()
            self._direct_mode = direct_mode
            if context is not None:
                self._set_context(context, name)
            if toplevel:
                assert context is None
                self._toplevel = True
                self._manager = Manager(self)
                layer.create_layer(self)
            else:
                assert context is not None

            self._pins = {}
            self._children = {}
            self._auto = set()
            if toplevel:
                toplevel_register.add(self)
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
        p = self._format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    @with_macro_mode
    def _add_child(self, childname, child):
        assert isinstance(child, (Context, Worker, CellLikeBase, Link))
        if isinstance(child, Context):
            assert child._context() is self
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

    @with_macro_mode
    def __setattr__(self, attr, value):
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
        raise AttributeError(attr)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._children:
            return True
        if attr in self._pins:
            return True
        return False

    def hasattr(self, attr):
        return self._hasattr(attr)

    def _part_of(self, ctx):
        assert isinstance(ctx, Context)
        if ctx is self:
            return True
        elif self._context is None:
            return False
        else:
            return self._context()._part_of(ctx)

    def _part_of2(self, ctx):
        assert isinstance(ctx, Context)
        p = ctx.path
        return self.path[:len(p)] == p

    def _root(self):
        if self._toplevel:
            return self
        return super()._root()

    def _is_sealed(self):
        return self._seal is not None

    def _flush_workqueue(self, full=True):
        from .macro import Macro
        manager = self._get_manager()
        manager.flush()
        finished = True
        children_unstable = set()
        if len(self.unstable_workers):
            finished = False
        for childname, child in self._children.items():
            if isinstance(child, (Context, Macro)):
                if full:
                    child_finished, _ = child._flush_workqueue(full=True)
                    if not child_finished:
                        mgr = child._get_manager()
                        remaining = list(mgr.unstable) + list(mgr.children_unstable)
                        children_unstable.update(remaining)
                        finished = False
                else:
                    child_finished = child._flush_workqueue(full=False)
                    if not child_finished:
                        finished = False
        if full:
            manager.mountmanager.tick()
            manager.children_unstable = children_unstable
            return finished, children_unstable
        else:
            return finished

    def equilibrate(self, timeout=None, report=0.5):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds, returning the remaining set of unstable workers
        Report the workers that are not stable every "report" seconds
        """
        if get_macro_mode():
            raise Exception("ctx.equilibrate() will not work in macro mode")
        assert self._get_manager().active
        start_time = time.time()
        last_report_time = start_time
        finished, _ = self._flush_workqueue()

        if self._destroyed:
            return set()
        if finished:
            return set()
        last_unstable = set()
        while 1:
            if self._destroyed:
                return set()
            curr_time = time.time()
            if curr_time - last_report_time > report:
                manager = self._get_manager()
                unstable = self.unstable_workers
                if last_unstable != unstable:
                    last_unstable = unstable
                    print("Equilibrate: waiting for:", self.unstable_workers)
                last_report_time = curr_time
            if timeout is not None:
                if curr_time - start_time > timeout:
                    break
            finished1, _ = self._flush_workqueue()
            if self._destroyed:
                return set()
            manager = self._get_manager()
            len1 = len(manager.unstable)
            time.sleep(0.001)
            finished2, children_unstable = self._flush_workqueue()
            if self._destroyed:
                return set()
            manager = self._get_manager()
            len2 = len(manager.unstable)
            manager.children_unstable = children_unstable
            if finished1 and finished2:
                if len1 == 0 and len2 == 0:
                    break
        if self._destroyed:
            return set()
        manager = self._get_manager()
        manager.flush()
        if self._destroyed:
            return set()
        return self._manager.unstable & self._manager.children_unstable

    @property
    def unstable_workers(self):
        """All unstable workers (not in equilibrium)"""
        from . import SeamlessBaseList
        result = list(self._manager.unstable) + list(self._manager.children_unstable)
        return SeamlessBaseList(sorted(result, key=lambda p:p._format_path()))

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

    def mount(self, path=None, mode="rw", authority="cell", persistent=False):
        """Performs a "lazy mount"; context is mounted to the directory path when macro mode ends
        path: directory path (can be None if an ancestor context has been mounted)
        mode: "r", "w" or "rw" (passed on to children)
        authority: "cell", "file" or "file-strict" (passed on to children)
        persistent: whether or not the directory persists after the context has been destroyed
                    The same setting is applied to all children
                    May also be None, in which case the directory is emptied, but remains
        """
        assert self._mount is None #Only the mountmanager may modify this further!
        if self._root()._direct_mode:
            raise Exception("Root context must have been constructed in macro mode")
        self._mount = {
            "autopath": False,
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        MountItem(None, self, dummy=True, **self._mount) #to validate parameters

    def __dir__(self):
        result = []
        result[:] = self._methods
        any_exported = any([c._exported for c in self._children.values()])
        for k, c in self._children.items():
            if k in result:
                continue
            if not any_exported or c._exported:
                result.append(k)
        return result

    @property
    def self(self):
        return _ContextWrapper(self)

    @property
    def internal_children(self):
        return _InternalChildrenWrapper(self)

    def destroy(self, from_del=False):
        from .macro import Macro
        self._unmount(from_del=from_del)
        if self._destroyed:
            return
        object.__setattr__(self, "_destroyed", True)
        for childname, child in self._children.items():
            if isinstance(child, (Context, Worker)):
                child.destroy(from_del=from_del)
        self._manager.destroy(from_del=from_del)
        if self._toplevel:
            toplevel_register.remove(self)

    def _unmount(self, from_del=False):
        """Unmounts a context while the mountmanager is reorganizing (during macro execution)
        The unmount will set all x._mount to None, but only if and when the reorganization succeeds
        """
        from .macro import Macro
        if self._unmounted:
            return
        object.__setattr__(self, "_unmounted" , True) #can be outside macro mode
        mountmanager = self._manager.mountmanager
        for childname, child in self._children.items():
            if isinstance(child, (Cell, Link)):
                if not is_dummy_mount(child._mount):
                    if not from_del:
                        assert mountmanager.reorganizing
                    mountmanager.unmount(child, from_del=from_del)
        for childname, child in self._children.items():
            if isinstance(child, (Context, Macro)):
                child._unmount(from_del=from_del)
        if not is_dummy_mount(self._mount):
            mountmanager.unmount_context(self, from_del=True)

    def _remount(self):
        """Undo an _unmount"""
        from .macro import Macro
        object.__setattr__(self, "_unmounted" , False) #can be outside macro mode
        for childname, child in self._children.items():
            if isinstance(child, (Context, Macro)):
                child._remount()

    def full_destroy(self, from_del=False):
        #all work buffers (work queue and manager work buffers) are now empty
        # time to free memory
        from .macro import Macro
        path = self.path
        for childname, child in self._children.items():
            if isinstance(child, Worker):
                child.full_destroy(from_del=from_del)
            if isinstance(child, (Context, Macro)):
                child.full_destroy(from_del=from_del)
        if self._toplevel:
            layer.destroy_layer(self)

    def __del__(self):
        if self._destroyed:
            return
        self.__dict__["_destroyed"] = True
        print("Undestroyed %s, mount points may remain" % self)
        #self.destroy(from_del=True)
        #self.full_destroy(from_del=True)


Context._methods = [m for m in Context.__dict__ if not m.startswith("_") \
      and m not in ("destroy", "full_destroy") ]
Context._methods += [m for m in SeamlessBase.__dict__  if not m.startswith("_") \
      and m != "StatusFlags" and m not in ("destroy", "full_destroy") \
      and m not in Context._methods]

def context(**kwargs):
    ctx = Context(**kwargs)
    return ctx
context.__doc__ = Context.__init__.__doc__

class _ContextWrapper:
    _methods = Context._methods + ["destroy", "full_destroy"]
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

class _InternalChildrenWrapper:
    def __init__(self, wrapped):
        super().__setattr__("_wrapped", wrapped)
    def __getattr__(self, attr):
        children = getattr(self._wrapped, "_children")
        if attr not in children:
            raise AttributeError(attr)
        return children[attr]
    def __dir__(self):
        children = getattr(self._wrapped, "_children")
        return list(children.keys())
    def __setattr__(self, attr, value):
        raise AttributeError("_InternalChildrenWrapper is read-only")

from . import Link
from .cell import Cell, CellLikeBase
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase

from .manager import Manager
from . import layer
from .layer import Path

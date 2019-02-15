"""Module for Context class."""
from weakref import WeakValueDictionary
from collections import OrderedDict
import time
import asyncio
from contextlib import contextmanager

from . import SeamlessBase
from .macro_mode import get_macro_mode, curr_macro, toplevel_register
from .mount import is_dummy_mount, MountItem, scan as mount_scan


class StatusReport(dict):
    def __str__(self):
        result = {}
        for k,v in self.items():
            result[k] = str(v)
        return "Status: " + str(result)
    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))

class Context(SeamlessBase):
    """Context class. Organizes your cells and workers hierarchically.
    """

    _name = None
    _children = {}
    _manager = None    
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"
    _mount = None
    _unmounted = False
    _macro = None # The macro that created this context

    def __init__(
        self, *,
        toplevel=False,
        mount=None,
    ):
        """Construct a new context.

A context can contain cells, workers (= transformers, reactors and macros),
and other contexts.

**Important methods and attributes**:
    ``.equilibrate()``, ``.status``

Parameters
----------
name: str
    name of the context within the parent context
"""
        super().__init__()
        if toplevel:
            self._toplevel = True
            self._manager = Manager(self)
        if mount is not None:
            if not get_macro_mode():
                self._mount = {
                    "autopath": False,
                    "path": mount,
                    "mode": "rw",
                    "authority": "file",
                    "persistent": True
                }
                MountItem(None, self, dummy=True, **self._mount) #to validate parameters
                mount_scan(self)
            else:
                self.mount(mount)
        self._children = {}
        self._auto = set()
        if toplevel:
            toplevel_register.add(self)
        from .. import communionserver
        if toplevel:
            communionserver.register_manager(self._manager)

    def _set_context(self, context, name):
        assert not self._toplevel
        super()._set_context(context, name)
        assert self._context() is context
        context_name = context._name
        if context_name is None:
            context_name = ()
        self._name = context_name + (name,)

    def _get_manager(self):
        assert self._toplevel or self._context is not None  #context must have a parent, or be toplevel
        return self._root()._manager

    def __str__(self):
        p = self._format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _add_child(self, childname, child):
        from .unbound_context import UnboundContext
        if not isinstance(child, (Context, UnboundContext, Worker, Cell, Link, StructuredCell)):
            raise TypeError(child, type(child))
        if isinstance(child, Context):
            assert child._context is None
        self._children[childname] = child
        child._set_context(self, childname)
        if not get_macro_mode():
            if not isinstance(child, Worker):
                mount_scan(child)
        

    def _add_new_cell(self, cell):
        assert isinstance(cell, Cell)
        assert cell._context is None
        count = 0
        while 1:
            count += 1
            cell_name = "cell" + str(count)
            if not self._hasattr(cell_name):
                break
        self._auto.add(cell_name)
        self._add_child(cell_name, cell)
        return cell_name

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._children and self._children[attr] is not value:
            msg = "Cannot re-assign to child '%s', do you mean child.set(...)?"
            raise AttributeError(msg % attr)
        self._add_child(attr, value)

    def __getattr__(self, attr):
        if attr in self._children:
            return self._children[attr]
        raise AttributeError(attr)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._children:
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
        if self._macro is not None:
            return self._macro._root()
        return super()._root()

    @property
    def path(self):
        if self._macro is not None:
            return self._macro.path + (self.name,)
        else:
            return super().path

    def _cache_paths(self):
        for child in self._children.values():
            child._cached_path = None
            child._cached_path = child.path
            if isinstance(child, (Context, UnboundContext)):
                child._cache_paths()


    def _flush_workqueue(self):
        manager = self._get_manager()
        manager.flush()
        finished = True
        if len(self.unstable_workers):
            finished = False
        return finished

    def _get_macro(self):
        return self._macro

    def equilibrate(self, timeout=None, report=10):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds, returning the remaining set of unstable workers
        Report the workers that are not stable every "report" seconds
        """
        manager = self._get_manager()
        loop = asyncio.get_event_loop()
        coroutine = manager.equilibrate(timeout, report, path=self.path)
        future = asyncio.ensure_future(coroutine)
        loop.run_until_complete(future)
        return future.result()
        
    @property
    def unstable_workers(self):
        """All unstable workers (not in equilibrium)"""
        from . import SeamlessBaseList
        result = list(self._manager.unstable)
        return SeamlessBaseList(sorted(result, key=lambda p:p._format_path()))

    @property
    def status(self):
        """The computation status of the context
        Returns a dictionary containing the status of all children that are not OK.
        If all children are OK, returns OK
        """
        result = StatusReport()
        for childname, child in self._children.items():
            if childname in self._auto:
                continue
            s = child.status
            if s != "OK" and s != "FINISHED":
                result[childname] = s
        if len(result):
            return result
        else:
            return "OK"

    def mount(self, path=None, mode="rw", authority="cell", persistent=False):
        if not get_macro_mode():
            if self._toplevel:
                msg = "In direct mode, toplevel contexts must be mounted at construction"
                raise Exception(msg)
            if self._context is not None and isinstance(self._context(), Context):
                msg = "In direct mode, mounting must happen before a context is assigned to a parent"
                raise Exception(msg)
        self._mount = {
            "autopath": False,
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        MountItem(None, self, dummy=True, **self._mount) #to validate parameters
        if not get_macro_mode():
            mount_scan(self)
        return self

    def __dir__(self):
        result = []
        result[:] = self._methods
        for k, c in self._children.items():
            if k in result:
                continue
            result.append(k)
        return result

    @property
    def self(self):
        return _ContextWrapper(self)

    @property
    def internal_children(self):
        return _InternalChildrenWrapper(self)

    def destroy(self, from_del=False):
        self._unmount(from_del=from_del)
        if self._destroyed:
            return
        object.__setattr__(self, "_destroyed", True)
        for childname, child in self._children.items():
            if isinstance(child, (Cell, Context, Worker)):
                child.destroy(from_del=from_del)
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
        manager = self._root()._manager
        mountmanager = manager.mountmanager
        for childname, child in self._children.items():
            if isinstance(child, (Cell, Link)):
                if not is_dummy_mount(child._mount):
                    raise NotImplementedError ### cache branch
                    if not from_del:
                        assert mountmanager.reorganizing
                    mountmanager.unmount(child, from_del=from_del)
        for childname, child in self._children.items():
            if isinstance(child, (Context, Macro)):
                child._unmount(from_del=from_del)
        if not is_dummy_mount(self._mount) or self._root() is self:
            mountmanager.unmount_context(self, from_del=True)

    def _remount(self):
        """Undo an _unmount"""
        raise NotImplementedError ### cache branch
        object.__setattr__(self, "_unmounted" , False) #can be outside macro mode
        for childname, child in self._children.items():
            if isinstance(child, (Context, Macro)):
                child._remount()

    def full_destroy(self, from_del=False):
        #all work buffers (work queue and manager work buffers) are now empty
        # time to free memory
        raise NotImplementedError ### cache branch
        from .macro import Macro
        path = self.path
        for childname, child in self._children.items():
            if isinstance(child, Worker):
                child.full_destroy(from_del=from_del)
            if isinstance(child, (Context, Macro)):
                child.full_destroy(from_del=from_del)

    def __del__(self):
        if self._destroyed:
            return
        self.__dict__["_destroyed"] = True
        print("Undestroyed %s, mount points may remain" % self)


Context._methods = [m for m in Context.__dict__ if not m.startswith("_") \
      and m not in ("destroy", "full_destroy") ]
Context._methods += [m for m in SeamlessBase.__dict__  if not m.startswith("_") \
      and m != "StatusFlags" and m not in ("destroy", "full_destroy") \
      and m not in Context._methods]

def context(**kwargs):
    if get_macro_mode():
        if curr_macro() is not None:
            assert "toplevel" not in kwargs or kwargs["toplevel"] == False        
        return UnboundContext(**kwargs)
    else:
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

from .unbound_context import UnboundContext
from .link import Link
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .structured_cell import StructuredCell

from .manager import Manager

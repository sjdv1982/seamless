"""Module for Context class."""
import weakref
from weakref import WeakValueDictionary
from collections import OrderedDict
import json
import time
import asyncio
from contextlib import contextmanager

from . import SeamlessBase
from .macro_mode import get_macro_mode, curr_macro, register_toplevel, unregister_toplevel
from .mount import is_dummy_mount, scan as mount_scan


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
        manager=None
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
        ''' #debugging
        try:
            raise Exception
        except Exception as exc:
            import traceback            
            self._EXC = "\n".join(traceback.format_stack())
        '''
        global Macro
        if Macro is None:
            from .macro import Macro
        global shareserver
        if shareserver is None:
            from .share import shareserver
        super().__init__()
        if manager is not None:
            assert toplevel
        if toplevel:
            self._toplevel = True
            if manager is None:
                manager = Manager()
            manager.add_context(self)
            self._manager = weakref.ref(manager)
        if mount is not None:
            mount_params = {
                "path": mount,
                "mode": "rw",
                "authority": "file",
                "persistent": True
            }
            self.mount(**mount_params)
        self._children = {}
        self._auto = set()
        if toplevel:
            register_toplevel(self)

    def _set_context(self, context, name):
        assert not self._toplevel
        super()._set_context(context, name)
        assert self._context() is context
        context_name = context._name
        if context_name is None:
            context_name = ()
        self._name = context_name + (name,)

    def _get_manager(self):
        assert self._toplevel or self._context is not None or self._macro is not None #context must have a parent, or be toplevel, or have a macro
        root = self._root()
        if self._toplevel or root is self:
            manager = self._manager
            if manager is None:
                return None
            return manager()
        return root._get_manager()

    def __str__(self):
        p = self._format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _add_child(self, childname, child):
        assert not self._destroyed
        from .unbound_context import UnboundContext
        if isinstance(child, UnboundContext):
            raise TypeError("Cannot add an unbound context to a bound one")
        if not isinstance(child, (Context, Worker, Cell, Link, StructuredCell)):
            raise TypeError(child, type(child))
        if isinstance(child, Context):
            assert child._context is None
        self._children[childname] = child
        child._set_context(self, childname)
        if not get_macro_mode():
            if isinstance(child, (Cell, Context)):
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
        if self._macro is not None:
            return self._macro._root()
        if self._toplevel:
            return self
        return super()._root()

    @property
    def path(self):        
        if self._context is not None:
            return super().path        
        if self._macro is not None \
          and isinstance(self._macro, Macro):
            return self._macro.path + ("ctx",)
        else:
            return super().path

    def _cache_paths(self):
        for child in self._children.values():
            child._cached_path = None
            child._cached_path = child.path
            if isinstance(child, Context):
                child._cache_paths()
            if isinstance(child, Macro):
                cctx = child._gen_context
                if cctx is not None:
                    cctx._cache_paths()

    def _get_macro(self):
        return self._macro

    def equilibrate(self, timeout=None, report=2):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, equilibrate() will return after at most
         "timeout" seconds, returning the remaining set of unstable workers
        Report the workers that are not stable every "report" seconds
        """
        manager = self._get_manager()
        return manager.taskmanager.equilibrate(timeout, report)
        
    def _get_status(self):
        status = {}
        for childname, child in self._children.items():
            if isinstance(child, StructuredCell):
                continue
            if childname in self._auto:
                continue
            status[childname] = (child, child._get_status())
        return status

    @property
    def status(self):
        """The computation status of the context
        Returns a dictionary containing the status of all children that are not OK.
        If all children are OK, returns OK
        """
        from .status import format_context_status
        status = self._get_status()
        statustxt = format_context_status(status)
        if isinstance(statustxt, dict):
            statustxt = json.dumps(statustxt, indent=2, sort_keys=True)
        return "Status: " + statustxt

    def mount(self, path=None, mode="rw", authority="cell", persistent=False):
        if not get_macro_mode():
            msg = "Mounting contexts in direct mode is not possible"
            raise Exception(msg)

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
        if self._destroyed:
            return
        super().destroy(from_del=from_del)
        for childname, child in self._children.items():
            if isinstance(child, (Cell, Context, Worker)):
                child.destroy(from_del=from_del)
        if self._toplevel:
            from .macro import _global_paths
            manager = self._get_manager()
            paths = _global_paths.get(self, {})
            for path in paths.values():
                manager._destroy_macropath(path)
            lib_unregister_all(self)
            unregister_toplevel(self)
            shareserver.destroy_root(self)
            manager.remove_context(self)
        self._unmount(from_del=from_del)

    def _unmount(self, from_del=False, manager=None):
        from .macro import Macro
        if self._unmounted:
            return
        self._unmounted = True
        if manager is None:
            manager = self._root()._get_manager()
        mountmanager = manager.mountmanager
        if self._toplevel or not is_dummy_mount(self._mount):
            mountmanager.unmount_context(
                self, 
                from_del=from_del,
                toplevel=self._toplevel
            )

    def __del__(self):
        if self._destroyed:
            return
        self.__dict__["_destroyed"] = True
        ###print(self._EXC) # debugging
        print("Undestroyed %s (%s), mount points may remain" % (self, hex(id(self))))


Context._methods = [m for m in Context.__dict__ if not m.startswith("_") \
      and m not in ("destroy", ) ]
Context._methods += [m for m in SeamlessBase.__dict__  if not m.startswith("_") \
      and m != "StatusFlags" and m not in ("destroy",) \
      and m not in Context._methods]

def context(**kwargs):
    from .macro import Macro
    if get_macro_mode():
        macro = curr_macro()
        if macro is not None and isinstance(macro, Macro):
            assert "toplevel" not in kwargs or kwargs["toplevel"] == False        
        return UnboundContext(**kwargs)
    else:
        ctx = Context(**kwargs)
        return ctx
context.__doc__ = Context.__init__.__doc__

class _ContextWrapper:
    _methods = Context._methods + ["destroy"]
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
from .library import unregister_all as lib_unregister_all

from .manager import Manager
Macro = None # import later
shareserver = None # import later
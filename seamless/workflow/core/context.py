"""Module for Context class."""

from seamless import Checksum, Buffer
from seamless.checksum.json import json_dumps

from . import SeamlessBase
from .macro_mode import (
    get_macro_mode,
    curr_macro,
    register_toplevel,
    unregister_toplevel,
)

from seamless.checksum.buffer_cache import buffer_cache


class StatusReport(dict):
    def __str__(self):
        result = {}
        for k, v in self.items():
            if not isinstance(v, StatusReport):
                v = str(v)
            result[k] = v
        return "Status: " + str(result)

    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))


class Context(SeamlessBase):
    """Context class. Organizes your cells and workers hierarchically."""

    _name = None
    _children = {}
    _manager = None
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"
    _macro = None  # The macro that created this context
    _macro_root = None
    _root_highlevel_context = lambda self: None
    _synth_highlevel_context = lambda self: None
    _compilers = None
    _languages = None

    def __init__(self, *, toplevel=False, manager=None, compilers=None, languages=None):
        """Construct a new context.

        A context can contain cells, workers (= transformers, reactors and macros),
        and other contexts.

        **Important methods and attributes**:
            ``.compute()``, ``.status``

        Parameters
        ----------
        name: str
            name of the context within the parent context

        toplevel: bool
            whether the context is top-level or not

        manager: seamless.workflow.core.manager.Manager or None
            Managers can be shared between contexts, which can be practical for various caches
            If None, create a new manager

        compilers: dict or None
            Compiler specification. If None, workers will use seamless.workflow.core.compiler.compilers

        languages: dict or None
            Languages specification. If None, workers will use seamless.workflow.core.compiler.languages
        """
        from seamless.config import check_delegation

        super().__init__()
        if manager is not None:
            assert toplevel
        if toplevel:
            check_delegation()
            self._toplevel = True
            if manager is None:
                manager = Manager()
            manager.add_context(self)
            self._manager = manager
        self._children = {}
        self._auto = set()
        if compilers is not None:
            self._compilers = compilers
        if languages is not None:
            self._languages = languages
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
        manager = context._manager
        if manager is not None:
            self._set_manager(manager)
            if not get_macro_mode():
                mountmanager = manager.mountmanager
                mountmanager.scan(context._root())

    def _set_manager(self, manager):
        self._manager = manager
        for child in self._children.values():
            if isinstance(child, Context):
                child._set_manager(manager)

    def _get_manager(self):
        manager = self._manager
        if manager is None:
            return None
        return manager

    def __str__(self):
        p = self._format_path()
        if p == ".":
            p = "<toplevel>"
        ret = "Seamless context: " + p
        return ret

    def _add_child(self, childname, child):
        assert not self._destroyed

        if isinstance(child, UnboundContext):
            raise TypeError("Cannot add an unbound context to a bound one")
        if not isinstance(child, (Context, Worker, Cell, UniLink, StructuredCell)):
            raise TypeError(child, type(child))
        if isinstance(child, Context):
            assert child._context is None
        self._children[childname] = child
        child._set_context(self, childname)

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

    @property
    def children(self):
        result = {}
        for k in sorted(list(self._children.keys())):
            result[k] = self._children[k]
        return result

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._children and self._children[attr] is not value:
            msg = "Cannot re-assign to child '%s', do you mean child.set(...)?"
            raise AttributeError(msg % attr)
        self._add_child(attr, value)

    def __getattr__(self, attr):
        if attr in self._children:
            result = self._children[attr]
            if (
                isinstance(result, Context)
                and result._synth_highlevel_context() is not None
            ):
                from ..highlevel.synth_context import SynthContext

                return SynthContext(
                    result._synth_highlevel_context(),
                    self.path + (attr,),
                    context=result,
                )
            return result
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
        return self.path[: len(p)] == p

    def _root(self):
        if self._macro is not None and self._macro_root is not None:
            return self._macro_root
        if self._toplevel:
            return self
        return super()._root()

    @property
    def path(self):
        if self._context is not None:
            return super().path
        if self._macro is not None and isinstance(self._macro, Macro):
            return self._macro.path + ("ctx",)
        else:
            return super().path

    def _cache_paths(self):
        for child in self._children.values():
            child._cached_path = None
            child._cached_path = child.path
            if isinstance(child, Context):
                child._cache_paths()
            elif isinstance(child, Macro):
                cctx = child._gen_context
                if cctx is not None:
                    cctx._cache_paths()

    def _get_macro(self):
        return self._macro

    def compute(self, timeout=None, report=2):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, compute() will return after at most
         "timeout" seconds, returning the remaining set of unstable workers
        Report the workers that are not stable every "report" seconds
        """
        from .. import verify_sync_compute

        verify_sync_compute()
        manager = self._get_manager()
        manager.sharemanager.tick()
        return manager.taskmanager.compute(timeout, report)

    async def computation(self, timeout=None, report=2):
        """
        Run workers and cell updates until all workers are stable,
         i.e. they have no more updates to process
        If you supply a timeout, compute() will return after at most
         "timeout" seconds, returning the remaining set of unstable workers
        Report the workers that are not stable every "report" seconds
        """
        manager = self._get_manager()
        await manager.sharemanager.tick_async()
        return await manager.taskmanager.computation(timeout, report)

    def _get_status(self):
        status = {}
        for childname, child in self._children.items():
            if isinstance(child, StructuredCell):
                continue
            if childname in self._auto:
                continue
            if (
                isinstance(child, Context)
                and child._synth_highlevel_context() is not None
            ):
                child = getattr(self, childname)
                status[childname] = child.status
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
            statustxt = json_dumps(statustxt)
        return "Status: " + statustxt

    def __dir__(self):
        result = []
        result[:] = self._methods
        for k, c in self._children.items():
            if k in result:
                continue
            result.append(k)
        return result

    @property
    def internal_children(self):
        return _InternalChildrenWrapper(self)

    def _update_annotated_checksums(self, annotated_checksums0, *, skip_scratch):
        from .build_module import get_compiled_module_code

        manager = self._get_manager()
        livegraph = manager.livegraph
        for child in self._children.values():
            if isinstance(child, Context):
                child._update_annotated_checksums(
                    annotated_checksums0, skip_scratch=skip_scratch
                )
            elif isinstance(child, Macro):
                elision = livegraph.macro_elision.get(child)
                if elision is not None:
                    elision_result = elision.get_elision_result()
                    if elision_result is None:
                        return
                    elision_result_buffer = Buffer(elision_result, "plain")
                    elision_result_checksum = elision_result_buffer.get_checksum()
                    buffer_cache.cache_buffer(
                        elision_result_checksum, elision_result_buffer
                    )
                    annotated_checksums0[elision_result_checksum.hex()] = False

                cctx = child._gen_context
                if cctx is not None:
                    cctx._update_annotated_checksums(
                        annotated_checksums0, skip_scratch=skip_scratch
                    )

            if not isinstance(child, Cell):
                continue

            if skip_scratch and child._scratch:
                continue

            checksum = Checksum(child.checksum)
            if not checksum:
                continue

            if child.celltype == "plain":
                compiled_module_code_checksum, compiled_module_code = (
                    get_compiled_module_code(checksum)
                )
                if compiled_module_code is not None:
                    buffer_cache.cache_buffer(
                        compiled_module_code_checksum, compiled_module_code
                    )
                    annotated_checksums0[compiled_module_code_checksum.hex()] = False
            has_independence = child.has_independence()
            if not annotated_checksums0.get(checksum, False):
                annotated_checksums0[checksum] = has_independence

    def save_vault(self, dirname: str, *, flat=False):
        """Save the checksum-to-buffer cache for the current graph in a vault directory

        If flat=True, buffers are directly written into that directory, else they are organized by dependence and size.
        """
        # TODO: option to not follow deep cell checksums (currently, they are always followed)
        manager = self._get_manager()
        assert manager is not None
        annotated_checksums0 = {}
        self._update_annotated_checksums(annotated_checksums0, skip_scratch=True)
        annotated_checksums = [
            (checksum, not has_independence)
            for checksum, has_independence in annotated_checksums0.items()
        ]
        checksums = [c[0] for c in annotated_checksums]
        buffer_dict = get_buffer_dict_sync(manager, checksums)
        if flat:
            save_vault_flat(dirname, annotated_checksums, buffer_dict)
        else:
            save_vault(dirname, annotated_checksums, buffer_dict)

    def destroy(self, *, from_del=False, manager=None):
        if self._destroyed:
            return
        if self._toplevel and manager is None:
            manager = self._get_manager()
        for childname, child in self._children.items():
            if isinstance(child, (Cell, Context, Worker, Macro)):
                child.destroy(from_del=from_del, manager=manager)
        super().destroy(from_del=from_del)
        highlevel_parent = self._synth_highlevel_context()
        if highlevel_parent is not None:
            path = self.path
            lp = len(path)
            for childname in list(highlevel_parent._children):
                if not isinstance(childname, tuple):
                    continue
                if childname[:lp] == path:
                    highlevel_parent._children.pop(childname)
        if self._toplevel:
            from .macro import _global_paths

            manager = self._get_manager()
            paths = _global_paths.get(self, {})
            for path in paths.values():
                manager._destroy_macropath(path)
            unregister_toplevel(self)
            manager.remove_context(self)
            manager.mountmanager.destroy_toplevel_context(self)
            if debugmountmanager is not None:
                debugmountmanager.remove_mounts(self)

    @property
    def exception(self):
        return None

    def __getitem__(self, attr):
        if not isinstance(attr, str):
            raise KeyError(attr)
        return getattr(self, attr)

    def __del__(self):
        if self._destroyed:
            return
        try:
            self.destroy()
        except Exception:
            import traceback

            traceback.print_exc()
            pass
        if self._destroyed:
            return
        self.__dict__["_destroyed"] = True
        print("Undestroyed %s (%s), mount points may remain" % (self, hex(id(self))))


Context._methods = [
    m for m in Context.__dict__ if not m.startswith("_") and m not in ("destroy",)
]
Context._methods += [
    m
    for m in SeamlessBase.__dict__
    if not m.startswith("_")
    and m != "StatusFlags"
    and m not in ("destroy",)
    and m not in Context._methods
]


def context(**kwargs):
    if get_macro_mode():
        macro = curr_macro()
        """
        if macro is not None and isinstance(macro, Macro):
            assert "toplevel" not in kwargs or kwargs["toplevel"] == False
        """
        return UnboundContext(**kwargs)
    else:
        ctx = Context(**kwargs)
        return ctx


context.__doc__ = Context.__init__.__doc__


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
from .unilink import UniLink
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .structured_cell import StructuredCell
from ..copying import get_buffer_dict_sync
from ..vault import save_vault, save_vault_flat

try:
    from ..metalevel.debugmount import debugmountmanager
except ImportError:
    debugmountmanager = None

from .manager import Manager
from .macro import Macro

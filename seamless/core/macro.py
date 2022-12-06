from collections import OrderedDict
import traceback

class ExecError(Exception): pass

class DummyContext:
    def __init__(self, path):
        self.path = path

from .worker import Worker, InputPin, OutputPin
class Macro(Worker):
    injected_modules = None
    allow_elision = False  # Do we honor elision keys?
                    # NOTE: for nested macros, allow_elision is determined by the top macro
    def __init__(self, macro_params):
        self._gen_context = None
        self._unbound_gen_context = None
        self.code = InputPin(self, "code", "python", "macro")
        self._pins = {"code":self.code}
        self._macro_params = OrderedDict()
        self.function_expr_template = "{0}\n{1}(ctx=ctx,"
        self.namespace = {}
        self.input_dict = {}  #pinname-to-accessor
        self._paths = {} #Path objects
        self._void = True
        self._in_elision = False
        super().__init__()
        forbidden = ("code",)
        for p in sorted(macro_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = macro_params[p]
            self._macro_params[p] = param
            celltype, subcelltype, as_ = None, None, None
            if isinstance(param, str):
                celltype = param
            elif isinstance(param, (list, tuple)):
                celltype = param[0]
                if len(param) > 1:
                    subcelltype = param[1]
                if len(param) > 2:
                    raise ValueError(param)
            elif isinstance(param, dict):
                celltype = param.get("celltype", celltype)
                subcelltype = param.get("subcelltype", subcelltype)
                as_ = param.get("as", None)
            else:
                raise ValueError((p, param))
            pin = InputPin(self, p, celltype, subcelltype, as_=as_)
            self.function_expr_template += "%s=%s," % (p, p)
            self._pins[p] = pin
        self.function_expr_template = self.function_expr_template[:-1] + ")"

    def _get_status(self):
        from .status import status_macro
        status = status_macro(self)
        return status

    @property
    def status(self):
        """The computation status of the macro"""
        from .status import format_worker_status
        try:
            status = self._get_status()
            statustxt = format_worker_status(status)
        except Exception:
            statustxt = traceback.format_exc()
        return "Status: " + str(statustxt)

    @property
    def exception(self):
        if not self._void:
            return None
        if self._status_reason != StatusReasonEnum.ERROR:
            return None
        manager = self._get_manager()
        cachemanager = manager.cachemanager
        return cachemanager.macro_exceptions[self]

    def _execute(self, code, values, module_workspace):
        from .HighLevelContext import HighLevelContext
        from .context import Context
        manager = self._get_manager()
        ok = False
        assert self._gen_context is None
        try:    
            for path in list(self._paths.keys()):
                mp = self._paths.pop(path)
                mp.destroy() 
            unbound_ctx = None       
            ctx = None
            with macro_mode_on(self):
                unbound_ctx = UnboundContext(toplevel=False, macro=True)
                ubmanager = unbound_ctx._realmanager
                unbound_ctx._ubmanager = ubmanager
                assert unbound_ctx._get_manager() is not None
                self._unbound_gen_context = unbound_ctx
                keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
                self.namespace.clear()
                self.namespace["__name__"] = "macro"
                self.namespace["__package__"] = "macro"
                self.namespace.update(keep)
                self.namespace.update( self.default_namespace.copy())
                self.namespace["HighLevelContext"] = HighLevelContext
                self.namespace["ctx"] = unbound_ctx
                self.namespace.update(values)
                inputs = ["ctx"] +  list(values.keys())
                str_self = str(self)
                if len(str_self) > 80:
                    str_self = str_self[:35] + "..%d.." % (len(str_self)-70) + str_self[-35:]
                #print("Execute", str_self)
                hctx = self._root()._root_highlevel_context()
                if hctx is not None:
                    hctx._destroy_path(self.path + ("ctx",), runtime=True)
                identifier = str(self)
                if len(module_workspace):
                    with injector.active_workspace(module_workspace, self.namespace):
                        if callable(code):
                            code(unbound_ctx, self.namespace)
                        else:
                            exec_code(code, identifier, self.namespace, inputs, None)
                else:
                    if callable(code):
                        code(unbound_ctx, self.namespace)
                    else:
                        exec_code(code, identifier, self.namespace, inputs, None)
                if self.namespace["ctx"] is not unbound_ctx:
                    raise Exception("Macro must return ctx")

                pctx = self._context
                pmacro = self
                ctx_path = self.path + ("ctx",)
                lctx_path = len(ctx_path)
                paths = [(ctx_path + k,v) for k,v in self._paths.items()]

                def add_paths(pmacro_path, pmpaths):
                    for path, p in pmpaths.items():
                        if len(pmacro_path):
                            fullpath = pmacro_path + ("ctx",) + path
                        else:
                            fullpath = path
                        if fullpath[:lctx_path] == ctx_path:
                            paths.append((fullpath, p))

                while pctx is not None:
                    if pmacro is not pctx()._macro:
                        pmacro = pctx()._macro
                        if pmacro is None:
                            break
                        add_paths(pmacro.path, pmacro._paths)
                    pctx = pctx()._context
                root = self._root()
                add_paths((), _global_paths.get(root, {}))

                manager = self._get_manager()
                ub_cells = {ctx_path + k: v for k,v in ubmanager.cells.items()}
                for child in ubmanager._registered:
                    if not isinstance(child, UniLink):
                        continue
                    path = ctx_path + child.path
                    assert path not in ub_cells
                    ub_cells[path] = child.get_linked()
                newly_bound = []
                for path, p in paths:
                    if p._cell is not None:
                        mctx = p._cell._context()._macro._context()
                        if mctx._part_of(self._context()):
                            if p._macro is None and path not in ub_cells:
                                old_cell = p._cell
                                p._cell = None
                                manager.cancel_cell(old_cell, void=True)
                            p._cell = None
                    if path not in ub_cells:
                        continue
                    cell = ub_cells[path]
                    newly_bound.append((path, p))

                ctx = Context(toplevel=False)
                ctx._macro = self
                ctx._macro_root = self._root()
                ctx._manager = self._get_manager()
                unbound_ctx._bind(ctx)
                self._gen_context = ctx
                ok = True
        except Exception as exception:
            manager._set_macro_exception(self, exception)
            if ctx is not None:
                ctx.destroy()
            if unbound_ctx is not None:
                unbound_ctx._context = lambda: DummyContext(self.path) # KLUDGE
                unbound_ctx.name = "ctx" # KLUDGE
                unbound_ctx.destroy()
        finally:
            self._unbound_gen_context = None
        if ok:
            for path, p in paths:
                p._bind(None, trigger=True)
            for path, p in newly_bound:
                cell = ub_cells[path]
                p._bind(cell, trigger=True)
            manager._set_macro_exception(self, None)
        else:
            self._gen_context = None
        keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
        self.namespace.clear()
        self.namespace["__name__"] = "macro"
        self.namespace["__package__"] = "macro"
        self.namespace.update(keep)

    def _set_context(self, ctx, name):
        has_ctx = self._context is not None
        super()._set_context(ctx, name)
        if not has_ctx:
            self._get_manager().register_macro(self)

    def destroy(self, *, from_del, manager=None):
        if self._destroyed:
            return
        super().destroy(from_del=from_del)
        manager2 = self._get_manager()
        if not isinstance(manager2, UnboundManager):
            manager2._destroy_macro(self)
        if self._gen_context is not None:
            result = self._gen_context.destroy(from_del=from_del, manager=manager)
            self._gen_context = None
            return result

    @property
    def ctx(self):
        if get_macro_mode():
            current_macro = curr_macro()
            assert self._context() is not None
            try:
                path = Path(current_macro, self.path, manager=self._get_manager())
            except Exception:
                import traceback; traceback.print_exc(); raise
            return path.ctx
        if self._gen_context is None:
            raise AttributeError
        return self._gen_context

    def __str__(self):
        ret = "Seamless macro: " + self._format_path()
        return ret


class Path:
    def __new__(cls, macro, path, *, manager=None):
        if not isinstance(path, tuple):
            raise TypeError(path)
        for subpath in path:
            if subpath is None:
                raise TypeError(path)
        from .unbound_context import UnboundManager
        from .manager import Manager
        self = object.__new__(cls)
        self._macro = macro
        self._path = path
        self._incoming = False
        self._cell = None
        self._realmanager = manager
        if macro is None:
            assert manager is not None
            assert isinstance(manager, (Manager, UnboundManager)), type(manager)
            gpaths = _global_paths.get(self._root(), {})
            if path in gpaths:
                return gpaths[path]
            if self._root() not in _global_paths:
                _global_paths[self._root()] = gpaths
            gpaths[path] = self
        else:
            if path in macro._paths:
                return macro._paths[path]
            macro._paths[path] = self
        manager.register_macropath(self)
        return self

    @property
    def _destroyed(self):
        macro = self._macro
        if macro is not None and macro._destroyed:
            return True
        manager = self._get_manager()
        if manager is not None and manager._destroyed:
            return True
        return False

    def destroy(self, from_del=False, manager=None):
        if manager is None:
            manager = self._get_manager()
        if manager is not None:
            manager._destroy_macropath(self)

    def _get_macro(self):
        return self._macro

    def _get_manager(self):
        root = self._root()
        if root is None:
            return None
        return root._get_manager()

    def _root(self):
        from .unbound_context import UnboundManager
        if self._macro is not None:
            return self._macro._root()
        elif self._realmanager is not None:
            if isinstance(self._realmanager, UnboundManager):
                mctx = self._realmanager._ctx()
                if mctx is None:
                    return self._realmanager._root_
                root = mctx._root()
                return root
            else:
                root = self._realmanager.last_ctx()
                return root
        else:
            raise AttributeError

    @property
    def value(self):
        cell = self._cell
        if cell is None:
            raise AttributeError
        return cell.value

    @property
    def checksum(self):
        cell = self._cell
        if cell is None:
            raise AttributeError
        return cell.checksum

    @property
    def buffer(self):
        cell = self._cell
        if cell is None:
            raise AttributeError
        return cell.buffer

    @property
    def exception(self):
        cell = self._cell
        if cell is None:
            raise AttributeError
        return cell.exception

    def __getattr__(self, attr):
        if attr.startswith("_") or attr == "cell" or attr in Path.__dict__:
            raise AttributeError(attr)
        return Path(self._macro, self._path + (attr,), manager=self._realmanager)

    def connect(self, other):
        manager = self._realmanager
        if manager is None:
            if self._macro is not None and \
                self._macro._unbound_gen_context is not None:
                manager = self._macro._unbound_gen_context._root()._realmanager
            else:
                raise AttributeError
        return manager.connect(self, None, other, None)

    def _unbind(self):
        if self._destroyed:
            return
        assert self._cell is not None
        oldcell = self._cell
        assert oldcell._destroyed
        self._cell = None
        oldcell._paths.remove(self)
        manager = self._get_manager()
        livegraph = manager.livegraph
        for accessor in livegraph.macropath_to_downstream[self]:
            manager.cancel_accessor(
                accessor, True,
                reason=StatusReasonEnum.UNCONNECTED
            )
        if not oldcell._destroyed:
            self_independence = livegraph.has_independence(self)
            if not self_independence:
                manager.cancel_cell(
                    oldcell, void=True,
                    reason=StatusReasonEnum.UNDEFINED
                )

    def _bind(self, cell, trigger):
        from .manager.tasks.cell_update import CellUpdateTask
        from .manager.tasks.accessor_update import AccessorUpdateTask
        if self._destroyed:
            return
        if cell is self._cell:
            return
        if cell is not None:
            assert self._cell is None
        manager = self._get_manager()
        assert manager is not None, (self._root(), self._realmanager, self._macro)
        livegraph = manager.livegraph
        self_independence = livegraph.has_independence(self)
        oldcell = self._cell
        assert oldcell is None
        if cell is None:
            return
        if cell._structured_cell:
            raise NotImplementedError("Macro paths for structured cells are not supported")
        cell_independence = cell.has_independence()
        if not cell_independence and not self_independence:
            msg = "Cannot bind %s to %s: both have no independence"
            raise Exception(msg % (cell, self))
        for path in cell._paths:
            assert path is not self, self._path
        cell._paths.add(self)
        self._cell = cell
        if trigger:
            if self_independence:
                for accessor in livegraph.macropath_to_downstream[self]:
                    if not cell._void:
                        accessor._new_macropath = True
                        manager.cancel_accessor(accessor, void=False)
                if cell._checksum is not None:
                    CellUpdateTask(manager, cell).launch()
            checksum = cell._checksum
            if checksum is not None:
                livegraph.activate_bilink(self, checksum)
            else:
                livegraph.rev_activate_bilink(self)

            if not self_independence:
                up_accessor = livegraph.macropath_to_upstream[self]
                assert up_accessor is not None  # if no up accessor, how could we have no independence?
                upstream_cell = livegraph.accessor_to_upstream[up_accessor]
                if not upstream_cell._void:
                    up_accessor._new_macropath = True
                    manager.cancel_accessor(up_accessor, void=False)
                assert isinstance(upstream_cell, Cell)
                if upstream_cell._checksum is not None:
                    CellUpdateTask(manager, upstream_cell).launch()
        else:
            if cell_independence and not self_independence:  # bound cell loses independence
                manager.cancel_cell(cell, void=False)


    def __str__(self):
        ret = "(Seamless path: ." + ".".join([str(n) for n in  self._path])
        if self._macro is not None:
            ret += " from %s)" % str(self._macro)
        else:
            ret += ")"
        return ret

    def __repr__(self):
        return self.__str__()


def path(obj):
    from .unbound_context import UnboundManager
    try:
        manager = obj._get_manager()
        if not isinstance(manager, UnboundManager):
            manager = obj._realmanager
        if not isinstance(manager, UnboundManager):
            raise AttributeError
    except AttributeError:
        manager = None
    return Path(obj._macro, obj._path, manager=manager)

_global_paths = {} # Paths created in direct mode, or macro mode None

def replace_path(v, toplevel):
    if not isinstance(v, Path):
        return v
    c = v._cell
    if c is not None:
        return c
    gpaths = _global_paths.get(v._root(), {})
    if curr_macro() is None and v._path in gpaths:
        result = toplevel
        p = v._path
        while len(p):
            try:
                pp = p[0]
                if isinstance(result, Macro) and pp == "ctx":
                    pp = "_gen_context"
                result = getattr(result, pp)
                p = p[1:]
            except AttributeError:
                return None
            if isinstance(result, Path):
                return None
        return result


def create_path(cell):
    from .cell import Cell
    if isinstance(cell, Path):
        return cell
    if not isinstance(cell, Cell):
        raise TypeError(cell)
    path = cell.path
    current_macro = curr_macro()
    if current_macro is None:
        gpaths = _global_paths.get(cell._root(), {})
        if path in gpaths:
            return gpaths[path]
    else:
        if path in current_macro._paths:
            return current_macro._paths[path]
    path = Path(current_macro, path, manager=cell._get_manager())
    path._bind(cell, trigger=False)
    return path

def macro(params):
    return Macro(params)

from .transformer import transformer
from .reactor import reactor
from .cell import cell
from .structured_cell import StructuredCell
from .context import context
from .unilink import unilink
names = ("cell", "transformer", "context", "unilink",
 "reactor")
names += ("StructuredCell",)
names = names + ("macro", "path")
Macro.default_namespace = {n:globals()[n] for n in names}
Macro.default_namespace["HighLevelContext"] = None   # import later to avoid circular imports
Macro.default_namespace["HighlevelContext"] = None   # future alias for HighLevelContext

from .cell import Cell
from .unilink import UniLink
from .injector import macro_injector as injector
from .unbound_context import UnboundContext, UnboundManager
from .macro_mode import macro_mode_on, curr_macro, get_macro_mode
from .cached_compile import exec_code
from .status import StatusReasonEnum

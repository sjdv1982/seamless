from collections import OrderedDict
import traceback
import weakref

from .cell import Cell
from .worker import Worker, InputPin, OutputPin
from .protocol import content_types
from . import library
from .injector import macro_injector as injector
from .unbound_context import UnboundContext, UnboundManager
from .macro_mode import macro_mode_on, curr_macro, get_macro_mode
from .cached_compile import exec_code

class ExecError(Exception): pass

class Macro(Worker):
    injected_modules = None
    def __init__(self, macro_params, *, lib=None):
        self._gen_context = None
        self._unbound_gen_context = None
        self.code = InputPin(self, "code", "ref", "pythoncode", "transformer")
        self._pins = {"code":self.code}
        self._macro_params = OrderedDict()
        self.function_expr_template = "{0}\n{1}(ctx=ctx,"
        self.lib = lib
        self.namespace = {}
        self.input_dict = {}  #pinname-to-accessor
        self._paths = weakref.WeakValueDictionary() #Path objects
        super().__init__()
        injected_modules = []
        for p in sorted(macro_params.keys()):
            param = macro_params[p]
            self._macro_params[p] = param
            transfer_mode, access_mode, content_type = "copy", None, None
            if isinstance(param, str):
                transfer_mode = param
            elif isinstance(param, (list, tuple)):
                transfer_mode = param[0]
                if len(param) > 1:
                    access_mode = param[1]
                if len(param) > 2:
                    content_type = param[2]
            elif isinstance(param, dict):
                transfer_mode = param.get("transfer_mode", transfer_mode)
                access_mode = param.get("access_mode", access_mode)
                content_type = param.get("content_type", content_type)
            else:
                raise ValueError((p, param))
            if content_type is None and access_mode in content_types:
                content_type = access_mode
            pin = InputPin(self, p, transfer_mode, access_mode)
            if access_mode == "module":
                injected_modules.append(p)
            self.function_expr_template += "%s=%s," % (p, p)
            self._pins[p] = pin
        self.function_expr_template = self.function_expr_template[:-1] + ")"
        if len(injected_modules):
            raise NotImplementedError ### cache branch
            self.injected_modules = injected_modules
            injector.define_workspace(self, injected_modules)

    def _execute(self):
        from .context import Context
        manager = self._get_manager()
        values = {}        
        for pinname, accessor in self.input_dict.items():            
            expression = manager.build_expression(accessor)
            if expression is None:
                value = None
            else:
                value = manager.get_expression(expression)
            if pinname == "code":
                code = value
            else:
                if expression.access_mode == "mixed":
                    if value is not None:
                        value = value[2]
                values[pinname] = value
        ok = False
        try:
            old_paths = self._paths
            old_gen_context = self._gen_context
            self._paths = weakref.WeakValueDictionary()
            with macro_mode_on(self):
                unbound_ctx = UnboundContext(root=self._root())
                unbound_ctx._manager = UnboundManager(unbound_ctx)                
                assert unbound_ctx._get_manager() is not None
                self._unbound_gen_context = unbound_ctx
                keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
                self.namespace.clear()
                #self.namespace["__name__"] = self.name
                self.namespace["__name__"] = "macro"
                self.namespace.update(keep)
                self.namespace.update( self.default_namespace.copy())
                self.namespace["ctx"] = unbound_ctx
                self.namespace.update(values)
                #workspace = self if self.injected_modules else None
                #with injector.active_workspace(workspace):
                #    
                #        exec(code_object, self.namespace)
                inputs = ["ctx"] +  list(values.keys())
                macro = self
                while 1:
                    lib = macro.lib
                    if lib is not None:
                        break
                    macro = macro._context()._macro
                    if macro is None:
                        break
                print("Execute macro", lib)
                with library.bind(lib):
                    exec_code(code, str(self), self.namespace, inputs, None)                
                if self.namespace["ctx"] is not unbound_ctx:
                    raise Exception("Macro must return ctx")

                paths = [(k,v) for k,v in self._paths.items()]
                pctx = self._context
                pmacro = self
                ctx_path = self.path + ("ctx",)
                lctx_path = len(ctx_path)

                def add_paths(pmacro_path, pmpaths):
                    for path, p in pmpaths.items():
                        if len(pmacro_path):
                            fullpath = pmacro_path + ("ctx",) + path
                        else:
                            fullpath = path
                        if fullpath[:lctx_path] == ctx_path:
                            path2 = fullpath[lctx_path:]
                            paths.append((path2, p))

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
                ub_cells = unbound_ctx._manager.cells
                newly_bound = []
                for path, p in paths:
                    if p._cell is not None:
                        mctx = p._cell._context()._macro._context()
                        if mctx._part_of(self._context()):                            
                            if p._macro is None and path not in ub_cells:
                                manager.set_cell(p._cell, None, subpath=None)
                            p._cell = None
                    if path not in ub_cells:
                        continue
                    cell = ub_cells[path]
                    newly_bound.append((path, p))
                
                ctx = Context(toplevel=False)
                ctx._macro = self
                unbound_ctx._bind(ctx)
                self._gen_context = ctx
                ctx._cache_paths()
                ok = True
        except Exception as exception:
            manager.set_macro_exception(self, exception)
        finally:
            self._unbound_gen_context = None
            self._paths = old_paths
        if ok:
            if old_gen_context is not None:
                old_gen_context.destroy()
            for path, p in paths:
                p._bind(None, trigger=True)
            for path, p in newly_bound:
                cell = ub_cells[path]
                p._bind(cell, trigger=True)
            
    def _set_context(self, ctx, name):
        super()._set_context(ctx, name)
        self._get_manager().register_macro(self)

    def destroy(self, *, from_del):
        super().destroy(from_del=from_del)
        if not from_del:
            self._get_manager()._destroy_macro(self)
        if self._gen_context is not None:
            return self._gen_context.destroy(from_del)
        
    @property
    def ctx(self):        
        if get_macro_mode():
            current_macro = curr_macro()
            try:
                path = Path(current_macro, self.path, manager=self._get_manager())
            except:
                import traceback; traceback.print_exc(); raise
            return path.ctx
        assert self._gen_context is not None
        return self._gen_context

    def __str__(self):
        ret = "Seamless macro: " + self._format_path()
        return ret


class Path:
    def __new__(cls, macro, path, *, manager=None):
        if not isinstance(path, tuple):
            raise TypeError(path)
        from .unbound_context import UnboundManager
        from .manager import Manager
        self = object.__new__(cls)
        self._macro = macro
        self._path = path
        self._incoming = False
        self._cell = None
        self._manager = manager
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
            assert path not in macro._paths, path
            macro._paths[path] = self
        return self

    def _get_macro(self):
        return self._macro

    def _get_manager(self):
        return self._root()._get_manager()

    def _root(self):
        from .unbound_context import UnboundManager
        if self._macro is not None:
            return self._macro._root()
        elif self._manager is not None:
            if isinstance(self._manager, UnboundManager):
                root = self._manager._ctx()._root()
                return root
            else:
                root = self._manager.ctx()
                return root
        else:
            raise AttributeError

    def __getattr__(self, attr):
        if attr.startswith("_") or attr == "cell":
            raise AttributeError(attr)
        return Path(self._macro, self._path + (attr,), manager=self._manager)

    def connect(self, other):
        if self._cell is not None:
            return self._cell.connect(other)
        else:
            manager = self._manager
            if manager is None:
                if self._macro is not None and \
                  self._macro._unbound_gen_context is not None:
                    manager = self._macro._unbound_gen_context._manager
                else:
                    raise AttributeError
            return manager.connect_cell(self, other, None)

    def _bind(self, cell, trigger):
        if cell is self._cell:
            return
        if cell is not None:
            assert self._cell is None
        if self._cell is not None:
            self._cell._paths.remove(self)
        if cell is not None:
            for path in cell._paths:
                assert path is not self, self._path                
            cell._paths.add(self)
        if cell is None:
            manager = self._cell._get_manager()
        else:
            manager = cell._get_manager()
        self._cell = cell
        if trigger:
            if self._incoming and cell is not None:                
                upstream = manager._cell_upstream(cell, None)
                if isinstance(upstream, Cell):
                    a1 = manager.get_default_accessor(upstream)
                    a2 = manager.get_default_accessor(cell)
                    manager.update_accessor_accessor(a1, a2)
            if cell is not None:
                manager.update_path_value(self)
    
    def __str__(self):
        ret = "(Seamless path: ." + ".".join(self._path)
        if self._macro is not None:
            ret += " from %s)" % str(self._macro)
        return ret

    def __repr__(self):
        return self.__str__()


def path(obj):
    from .unbound_context import UnboundManager
    try:
        try:
            manager = obj._get_manager()
            if not isinstance(manager, UnboundManager):
                manager = obj._manager
        except AttributeError:
            manager = obj._manager
        if not isinstance(manager, UnboundManager):
            raise AttributeError
    except AttributeError:
        manager = None
    return Path(obj._macro, obj._path, manager=manager)

_global_paths = weakref.WeakKeyDictionary() # Paths created in direct mode, or macro mode None

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

def macro(params, *, lib=None):
    return Macro(params, lib=lib)

from . import cell, transformer, pytransformercell, \
 reactor, pyreactorcell, pymacrocell, plaincell, csoncell,  \
 arraycell, mixedcell, pythoncell, ipythoncell
from .library import libcell
from .structured_cell import StructuredCell
from .context import context
from .link import link
names = ("cell", "transformer", "context", "pytransformercell", "link", 
 "reactor", "pyreactorcell", "pymacrocell", "plaincell", "csoncell",
 "mixedcell", "arraycell", "pythoncell", "ipythoncell", "libcell")
names += ("StructuredCell",)
names = names + ("macro", "path")
Macro.default_namespace = {n:globals()[n] for n in names}

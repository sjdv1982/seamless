from collections import OrderedDict
import traceback
import weakref

from .worker import Worker, InputPin, OutputPin
from .protocol import content_types
from .injector import macro_injector as injector
from .unbound_context import UnboundContext
from .macro_mode import macro_mode_on
from .cached_compile import exec_code

class ExecError(Exception): pass

class Macro(Worker):
    injected_modules = None
    def __init__(self, macro_params, *, lib=None):
        self._gen_context = None
        self.code = InputPin(self, "code", "ref", "pythoncode", "transformer")
        self._pins = {"code":self.code}
        self._macro_params = OrderedDict()
        self.function_expr_template = "{0}\n{1}(ctx=ctx,"
        self.lib = lib
        self.namespace = {}
        self.input_dict = {}  #pinname-to-accessor
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
        if self.lib is not None:
            raise NotImplementedError ### cache branch
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
                values[pinname] = value
        with macro_mode_on(self):
            unbound_ctx = UnboundContext()
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
            #    with library.bind(self.lib):
            #        exec(code_object, self.namespace)
            inputs = ["ctx"] +  list(values.keys())
            exec_code(code, str(self), self.namespace, inputs, None)
            if self.namespace["ctx"] is not unbound_ctx:
                raise Exception("Macro must return ctx")

            ctx = Context(name="ctx", toplevel=False)
            ctx._set_context(self._context(), "MACRO:" + self.name + ".ctx")
            ctx._macro = self            
            unbound_ctx._bind(ctx)
            if self._gen_context is not None:
                self._gen_context.destroy()
            self._gen_context = ctx

    def _set_context(self, ctx, name):
        super()._set_context(ctx, name)
        self._get_manager().register_macro(self)

    def _unmount(self,from_del=False):
        if self._gen_context is not None:
            return self._gen_context._unmount(from_del)

    @property
    def ctx(self):
        return self._gen_context

    def __str__(self):
        ret = "Seamless macro: " + self._format_path()
        return ret


def macro(params, *, lib=None):
    return Macro(params, lib=lib)

from . import cell, transformer, pytransformercell, link, \
 reactor, pyreactorcell, pymacrocell, plaincell, csoncell,  \
 arraycell, mixedcell, pythoncell
from .structured_cell import StructuredCell, BufferWrapper
from .context import context
names = ("cell", "transformer", "context", "pytransformercell", "link", 
 "reactor", "pyreactorcell", "pymacrocell", "plaincell", "csoncell",
 "mixedcell", "arraycell", "pythoncell") #TODO: , "ipythoncell", "libcell", "libmixedcell") ### cache branch
names += ("StructuredCell", "BufferWrapper")
names = names + ("macro",)
Macro.default_namespace = {n:globals()[n] for n in names}

from collections import OrderedDict
import traceback

from .worker import Worker, InputPin, OutputPin
from .protocol import content_types
from .injector import macro_injector as injector
from .unbound_context import UnboundContext
from .macro_mode import macro_mode_on
from .cached_compile import cached_compile

class ExecError(Exception): pass

class Macro(Worker):
    injected_modules = None
    def __init__(self, macro_params, *, lib=None):
        self.gen_context = None
        self.macro_context_name = None
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
                identifier = str(self)
                try:
                    code_object = cached_compile(code, identifier, "exec")
                except Exception as exception:
                    manager.set_macro_exception(self, exception)
            else:
                values[pinname] = values
        with macro_mode_on(self):
            ctx = UnboundContext()
            keep = {k:v for k,v in self.namespace.items() if k.startswith("_")}
            self.namespace.clear()
            #self.namespace["__name__"] = self.name
            self.namespace["__name__"] = "macro"
            self.namespace.update(keep)
            self.namespace.update( self.default_namespace.copy())
            self.namespace["ctx"] = ctx
            self.namespace.update(values)
            #workspace = self if self.injected_modules else None
            #with injector.active_workspace(workspace):
            #    with library.bind(self.lib):
            #        exec(code_object, self.namespace)
            exec(code_object, self.namespace)
            if self.namespace["ctx"] is not ctx:
                raise Exception("Macro must return ctx")

        print("execute macro", self)

    def _set_context(self, ctx, name):
        super()._set_context(ctx, name)
        self._get_manager().register_macro(self)

    def _unmount(self,from_del=False):
        if self.gen_context is not None:
            return self.gen_context._unmount(from_del)

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

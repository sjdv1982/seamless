from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin
from .protocol import content_types
from .injector import macro_injector as injector


class ExecError(Exception): pass

class Macro(Worker):
    macro_tag = "MACRO_"
    injected_modules = None
    def __init__(self, macro_params, *, lib=None):
        self.gen_context = None
        self.macro_context_name = None
        self.code = InputPin(self, "code", "ref", "pythoncode", "transformer")
        self._pins = {"code":self.code}
        self._macro_params = OrderedDict()
        self.function_expr_template = "{0}\n{1}(ctx=ctx,"
        self.lib = lib
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
        self._missing = set(list(macro_params.keys())+ ["code"])
        if len(injected_modules):
            self.injected_modules = injected_modules
            injector.define_workspace(self, injected_modules)

    def __str__(self):
        ret = "Seamless macro: " + self._format_path()
        return ret


def macro(params, *, lib=None):
    return Macro(params, lib=lib)


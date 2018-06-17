from weakref import WeakSet
from contextlib import contextmanager
from collections import OrderedDict
import traceback

class MacroRegister:
    def __init__(self):
        self.stack = []
    def push(self):
        self.stack.append(WeakSet())
    def pop(self):
        return self.stack.pop()
    def add(self, item):
        self.stack[-1].add(item)

macro_register = MacroRegister()

_macro_mode = False
def get_macro_mode():
    return _macro_mode

@contextmanager
def macro_mode_on():
    global _macro_mode
    old_macro_mode = _macro_mode
    _macro_mode = True
    macro_register.push()
    try:
        yield
    finally:
        _macro_mode = old_macro_mode
    curr_macro_register = macro_register.pop()
    mount.resolve_register(curr_macro_register)

from .worker import Worker, InputPin, OutputPin

class Macro(Worker):
    active = False
    exception = None
    def __init__(self, macro_params):
        super().__init__()
        self.gen_context = None
        self.code = InputPin(self, "code", "ref", "pythoncode", "pytransformer")
        self._pins = {"code":self.code}
        self._message_id = 0
        self._macro_params = OrderedDict()
        self._values = {}
        self.code_object = None
        self.namespace = None
        self.function_expr_template = "{0}(ctx=ctx,"
        for p in sorted(macro_params.keys()):
            param = macro_params[p]
            self._macro_params[p] = param
            mode, submode = "copy", None
            if isinstance(param, str):
                mode = param
            elif isinstance(param, (list, tuple)):
                io = param[0]
                if len(param) > 1:
                    mode = param[1]
                if len(param) > 2:
                    submode = param[2]
            else:
                raise ValueError((p, param))
            pin = InputPin(self, p, mode, submode)
            self.function_expr_template += "%s=%s," % (p, p)
            self._pins[p] = pin
        self.function_expr_template = self.function_expr_template[:-1] + ")"
        self._missing = set(list(macro_params.keys())+ ["code"])

    def __str__(self):
        ret = "Seamless macro: " + self.format_path()
        return ret

    def execute(self):
        from .context import context
        #TODO: macro caching!!!
        assert self._context is not None
        macro_context_name = "macro_gen_" + self.name
        ctx = None
        try:
            self._pending_updates += 1
            with macro_mode_on():
                ctx = context(context=self._context, name=macro_context_name)
                self.namespace = self.default_namespace.copy()
                self.namespace["ctx"] = ctx
                self.namespace.update(self._values)
                exec(self.code_object, self.namespace)
                self._context._add_child(macro_context_name, ctx)
            self.exception = None
            if self.gen_context is not None:
                self.gen_context.destroy()
            self.gen_context = ctx
        except Exception as exc:
            traceback.print_exc()
            if self.exception is not None:
                self.exception = traceback.format_exc()
                if ctx is not None:
                    ctx.destroy()
        finally:
            self._pending_updates -= 1


    def receive_update(self, input_pin, value):
        if value is None:
            self._missing.add(input_pin)
            self._values[input_pin] = None
        else:
            if input_pin == "code":
                code = value.value
                func_name = value.func_name
                if value.is_function:
                    expr = self.function_expr_template.format(code, func_name)
                    self.code_object = compile(expr, func_name, "exec")
                else:
                    self.code_object = compile(code, func_name, "exec")
            else:
                self._values[input_pin] = value
            if input_pin in self._missing:
                self._missing.remove(input_pin)
            if not len(self._missing):
                self.execute()

    def _touch(self):
        if self.status() == self.StatusFlags.OK.name:
            self.execute()

    def _shell(self, submode):
        assert submode is None
        return self.namespace, self.code, str(self)

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    def status(self):
        """The computation status of the macro
        Returns a dictionary containing the status of all pins that are not OK.
        If all pins are OK, returns the status of the macro itself: OK or pending
        """
        result = {}
        for pinname, pin in self._pins.items():
            s = pin.status()
            if s != self.StatusFlags.OK.name:
                result[pinname] = s
        if len(result):
            return result
        if self.exception is not None:
            return self.StatusFlags.ERROR.name
        return self.StatusFlags.OK.name

    def activate(self):
        pass

def macro(params):
    return Macro(params)

from . import mount

from . import cell, transformer, context
names = "cell", "transformer", "context"
names = names + ("macro",)
Macro.default_namespace = {n:globals()[n] for n in names}

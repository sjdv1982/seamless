from . import RegistrarObject, BaseRegistrar
from ..cached_compile import cached_compile

class EvalRegistrarObject(RegistrarObject):

    def unregister(self):
        namespace = self.registrar._namespace
        for t in self.registered:
            if t in namespace:
                del namespace[t]
        self.registrar._unregister(self.context, self.data, self.data_name)

    def re_register(self, pythoncode):
        context = self.context
        if context is None:
            return self
        self.unregister()
        namespace = self.registrar._namespace
        variables_old = list(namespace.keys())
        title = self.data_name
        if title is None:
            title = "<string>"
        code = cached_compile(pythoncode, title, "exec")
        exec(code, namespace)
        registered_types = [v for v in namespace if v not in variables_old]
        updated_keys = [k for k in registered_types]
        updated_keys += [k for k in self.registered if k not in updated_keys and not k.startswith("__")]
        self.data = pythoncode
        self.registered = registered_types
        self.registrar.update(context, updated_keys)
        super().re_register(pythoncode)
        return self

class EvalRegistrar(BaseRegistrar):
    _register_type = ("text", "code", "python")
    _registrar_object_class = EvalRegistrarObject

    def __init__(self, namespace):
        self._namespace = namespace
        BaseRegistrar.__init__(self)

    #@macro(type=("text", "code", "python"), with_context=False,_registrar=True)
    def register(self, pythoncode, name=None):
        self._register(pythoncode, name)
        variables_old = list(self._namespace.keys())
        title = name
        if title is None:
            title = "<string>"
        code = cached_compile(pythoncode, title, "exec")
        exec(code, self._namespace)
        registered_types = [v for v in self._namespace if v not in variables_old and not v.startswith("__")]
        return self._registrar_object_class(self, registered_types, pythoncode, name)

    def get(self, key):
        return self._namespace[key]

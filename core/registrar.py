from .cached_compile import cached_compile
from .macro import macro
import weakref, ast
import types
from collections import OrderedDict
from .process import Managed

#TODO: ability to inherit from _registrars for subcontexts
#TODO: when cells are registered as ctx.registrar.x.register, they must be a
# part of ctx (ctx._part_of)
_registrars = {}

class RegistrarAccessor:
    def __init__(self, context, registrars=_registrars):
        self._context = weakref.ref(context)
        self._registrars = registrars
    def __getattr__(self, attr):
        return RegistrarProxy(self, self._registrars[attr])

class RegistrarProxy:
    def __init__(self, accessor, registrar):
        self._accessor = accessor
        self._registrar = registrar

    def __getattr__(self, attr):
        return getattr(self._registrar, attr)

    def update(self, update_keys):
        context = self._accessor._context()
        if context is None:
            return
        return self._registrar.update(context, update_keys)

    def connect(self, key, target, namespace_name = None):
        context = self._accessor._context()
        if context is None:
            return
        return self._registrar.connect(context, key, target, namespace_name)

class BaseRegistrar:
    name = None
    _register_type = None
    def __init__(self):
        cls = self.__class__
        #monkeypatch until I properly learn to get the method binding working
        self.register = types.MethodType(
          macro(type=OrderedDict(
            _arg1="self",
            _arg2=cls._register_type,
          ),
          with_context=False)
          (cls.register),
          self
        )

    def update(self, context, update_keys):
        manager = context._manager
        for key in update_keys:
            manager.update_registrar_key(self, key)

    def connect(self, context, key, target, namespace_name):
        manager = context._manager
        if namespace_name is None:
            namespace_name = key
        manager.add_registrar_listener(self, key, target, namespace_name)
        target.receive_registrar_update(self.name, key, namespace_name)

    def get(self, key):
        raise NotImplementedError

class RegistrarObject(Managed):
    registrar = None
    registered = []

    def __init__(self, registrar, registered):
        from .macro import get_macro_mode
        from .context import get_active_context
        if get_macro_mode():
            ctx = get_active_context()
            ctx._add_new_registrar_object(self)
        self.registrar = registrar
        self.registered = registered
        super().__init__()

    def unregister(self):
        raise NotImplementedError

    def re_register(self, value):
        raise NotImplementedError

    def destroy(self):
        if self._destroyed:
            return
        self.unregister()
        super().destroy()

class SilkRegistrar(BaseRegistrar):
    #TODO: setting up private Silk namespaces for subcontexts
    _register_type = ("text", "code", "silk")

    #@macro(type=("text", "code", "silk"), with_context=False)
    def register(self,silkcode):
        from seamless import silk
        registered_types = silk.register(silkcode)
        return SilkRegistrarObject(self, registered_types)

    def get(self, key):
        from seamless.silk import Silk
        try:
            return getattr(Silk, key)
        except AttributeError:
            raise KeyError(key)

class SilkRegistrarObject(RegistrarObject):

    def unregister(self):
        from seamless import silk
        silk.unregister(self.registered)

    def re_register(self, silkcode):
        context = self.context
        if context is None:
            return
        self.unregister()
        from seamless import silk
        registered_types = silk.register(silkcode)
        updated_keys = [k for k in registered_types]
        updated_keys += [k for k in self.registered if k not in updated_keys]
        updated_keys2 = []
        updated_keys2 += updated_keys
        for ar in 1,2,3:
            for k in updated_keys:
                updated_keys2.append(k + ar * "Array")
        #TODO: figure out dependent types and add them
        self.registered = registered_types
        self.registrar.update(context, updated_keys2)
        return self

class EvalRegistrar(BaseRegistrar):
    _register_type = ("text", "code", "python")

    def __init__(self, namespace):
        self._namespace = namespace
        BaseRegistrar.__init__(self)

    #@macro(type=("text", "code", "python"), with_context=False)
    def register(self, pythoncode, name=None):
        variables_old = list(self._namespace.keys())
        code = cached_compile(pythoncode, "<string>", "exec")
        exec(code, self._namespace)
        registered_types = [v for v in self._namespace if v not in variables_old]
        return EvalRegistrarObject(self._namespace, registered_types)

    def get(self, key):
        return self._namespace[attr]

class EvalRegistrarObject(RegistrarObject):

    def unregister(self):
        namespace = self.registrar._namespace
        for t in self.registered:
            if t in namespace:
                del namespace[t]

    def re_register(self, pythoncode):
        context = self.context
        if context is None:
            return
        self.unregister()
        namespace = self.registrar._namespace
        variables_old = list(namespace.keys())
        code = cached_compile(pythoncode, "<string>", "exec")
        exec(code, namespace)
        registered_types = [v for v in namespace if v not in variables_old]
        updated_keys = [k for k in registered_types]
        updated_keys += [k for k in self.registered if k not in updated_keys]
        #TODO: for hive, figure out dependencies and add them
        self.registered = registered_types
        self.registrar.update(context, updated_keys)

def add_registrar(name, registrar):
    assert isinstance(registrar, BaseRegistrar)
    assert name not in _registrars, name
    registrar.name = name
    _registrars[name] = registrar

add_registrar("silk", SilkRegistrar())
add_registrar("hive", EvalRegistrar({}))

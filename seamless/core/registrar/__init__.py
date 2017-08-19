from ..cached_compile import cached_compile
from ..macro import macro
import weakref, ast
import types
from collections import OrderedDict
from .. import Managed

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
        #or until never, because the macro needs self, too
        self.register = types.MethodType(
          macro(
            type=OrderedDict(
              _arg1="self",
              _arg2=cls._register_type,
            ),
            with_context=False,
            registrar=self
          )
          (cls.register),
          self
        )

    def register(self,*args, **kwargs):
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError

    def _register(self, data, data_name):
        from ..context import get_active_context
        ctx = get_active_context()
        if ctx is None:
            return
        manager = ctx._manager
        manager.add_registrar_item(self.name, self._register_type, data, data_name)

    def _unregister(self, data, data_name):
        from ..context import get_active_context
        ctx = get_active_context()
        if ctx is None:
            return
        manager = ctx._manager
        try: ###
            manager.remove_registrar_item(self.name, self._register_type, data, data_name)
        except Exception:
            pass


    def update(self, context, update_keys):
        manager = context._manager
        for key in update_keys:
            manager.update_registrar_key(self, key)

    def connect(self, context, key, target, namespace_name):
        from ..worker import Worker
        from ..context import Context, get_active_context
        from ..macro import _macro_registrar
        manager = context._manager
        if isinstance(target, Worker):
            if namespace_name is None:
                namespace_name = key
            manager.add_registrar_listener(self, key, target, namespace_name)
            target.receive_registrar_update(self.name, key, namespace_name)
        elif isinstance(target, Context):
            assert namespace_name is None
            assert target is get_active_context(), (target, get_active_context)
            _macro_registrar.append((self, manager, key))
        else:
            raise TypeError(target)

    def get(self, key):
        raise NotImplementedError

class RegistrarObject(Managed):
    registrar = None
    registered = []

    def __init__(self, registrar, registered, data, data_name):
        from ..macro import get_macro_mode
        from ..context import get_active_context
        if get_macro_mode():
            ctx = get_active_context()
            ctx._add_new_registrar_object(self)
        assert isinstance(registrar, BaseRegistrar)
        self.registrar = registrar
        self.registered = registered
        self.data = data
        self.data_name = data_name
        super().__init__()

    def unregister(self):
        raise NotImplementedError

    def re_register(self, value):
        self.data = value
        return self

    def destroy(self):
        if self._destroyed:
            return
        self.unregister()
        super().destroy()

def add_registrar(name, registrar):
    assert isinstance(registrar, BaseRegistrar)
    assert name not in _registrars, name
    registrar.name = name
    _registrars[name] = registrar

from .silkregistrar import SilkRegistrar
from .evalregistrar import EvalRegistrar

add_registrar("silk", SilkRegistrar())
add_registrar("python", EvalRegistrar({}))

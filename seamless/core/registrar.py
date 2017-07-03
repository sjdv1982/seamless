from .cached_compile import cached_compile
from .macro import macro
import weakref, ast
import types
from collections import OrderedDict
from . import Managed

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
        from .context import get_active_context
        ctx = get_active_context()
        if ctx is None:
            return
        manager = ctx._manager
        manager.add_registrar_item(self.name, self._register_type, data, data_name)

    def _unregister(self, data, data_name):
        from .context import get_active_context
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
        from .worker import Worker
        from .context import Context, get_active_context
        from .macro import _macro_registrar
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
        from .macro import get_macro_mode
        from .context import get_active_context
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

class SilkRegistrarObject(RegistrarObject):

    def unregister(self):
        from seamless import silk
        silk.unregister(self.registered)
        self.registrar._unregister(self.data, self.data_name)

    def re_register(self, silkcode):
        context = self.context
        if context is None:
            return self
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
        self.registrar._register(self.data,self.data_name)
        super().re_register(silkcode)
        return self

class SilkRegistrar(BaseRegistrar):
    #TODO: setting up private Silk namespaces for subcontexts
    _register_type = ("text", "code", "silk")
    _registrar_object_class = SilkRegistrarObject

    #@macro(type=("text", "code", "silk"), with_context=False,_registrar=True)
    def register(self,silkcode, name=None):
        self._register(silkcode,name)
        from seamless import silk
        registered_types = silk.register(silkcode)
        return self._registrar_object_class(self, registered_types, silkcode, name)

    def get(self, key):
        from seamless.silk import Silk
        try:
            return getattr(Silk, key)
        except AttributeError:
            raise KeyError(key)

class EvalRegistrarObject(RegistrarObject):

    def unregister(self):
        namespace = self.registrar._namespace
        for t in self.registered:
            if t in namespace:
                del namespace[t]
        self.registrar._unregister(self.data, self.data_name)

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

class GLShaderRegistrarObject(RegistrarObject):

    def __init__(self, registrar, registered, data, data_name):
        super().__init__(registrar, registered, data, data_name)
        self._bound = False
        self._shader_id = None
        self._parse(data)

    @property
    def shader_id(self):
        return self._shader_id

    def unregister(self):
        self.destroy()
        namespace = self.registrar._namespace
        t = self.data_name
        if t in namespace:
            del namespace[t]

        self.registrar._unregister(self.data, t)

    def re_register(self, gl_shader):
        self.destroy()
        self._parse(gl_shader)
        super().re_register(gl_shader)
        return self

    def _parse(self, gl_shader):
        #TODO: STUB!
        self.gl_shader = gl_shader

    def bind(self):
        from .. import opengl
        if self._bound:
            return

        self._bound = True

    def destroy():
        from .. import opengl
        if self._destroyed:
            return
        if self._bound and opengl():
            pass #TODO: clean up shaders
        super().destroy()

class GLShaderRegistrar(BaseRegistrar):
    _register_type = "json"
    _registrar_object_class = GLShaderRegistrarObject
    def register(self, gl_shader):
        name = gl_shader["name"]
        shader_obj = self._registrar_object_class(self, [name], gl_shader, name)
        self._namespace[name] = shader_obj
        return shader_obj

def add_registrar(name, registrar):
    assert isinstance(registrar, BaseRegistrar)
    assert name not in _registrars, name
    registrar.name = name
    _registrars[name] = registrar

add_registrar("silk", SilkRegistrar())
add_registrar("python", EvalRegistrar({}))

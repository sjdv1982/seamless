from .cached_compile import cached_compile
from .macro import macro
import weakref, ast
import types

#TODO: ability to inherit from _registrars for subcontexts
_registrars = {}

class RegistrarAccessor:
    def __init__(self, context):
        self._context = weakref.ref(context)
    def __getattr__(self, attr):
        return _registrars[attr]

class BaseRegistrar:
    #pass
    _register_type = None
    def __init__(self):
        cls = self.__class__
        #monkeypatch until I properly learn to get the method binding working
        self.register = types.MethodType(
          macro(type=cls._register_type, with_context=False)
          (cls.register),
          self
        )

class SilkRegistrar(BaseRegistrar):
    #TODO: setting up private Silk namespaces for subcontexts
    _register_type = ("text", "code", "silk")
    #@macro(type=("text", "code", "silk"), with_context=False)
    def register(self,silkcode):
        from seamless import silk
        silk.register(silkcode)
    def __getattr__(self, attr):
        from seamless.silk import Silk
        return getattr(Silk, attr)

class EvalRegistrar(BaseRegistrar):
    _register_type = ("text", "code", "python")
    def __init__(self, namespace):
        self._namespace = namespace
        BaseRegistrar.__init__(self)
    #@macro(type=("text", "code", "python"), with_context=False)
    def register(self, pythoncode, name=None):
        code = cached_compile(pythoncode, "<string>", "exec")
        exec(code, self._namespace)
    def __getattr__(self, attr):
        return self._namespace[attr]

def add_registrar(name, registrar):
    assert isinstance(registrar, BaseRegistrar)
    assert name not in _registrars, name
    _registrars[name] = registrar

add_registrar("silk", SilkRegistrar())
add_registrar("hive", EvalRegistrar({}))

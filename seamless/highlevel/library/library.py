import json, inspect

_libraries = {}

def validate_params(params):
    if params is None:
        return None
    result = {}
    for k, v in params.items():
        assert k not in ("code", "ctx")
        if isinstance(v, str):
            v = {"type": v}
        type_ = v.get("type", "value")
        assert type_ in ("value", "cell"), (k, type_)
        io = v.get("io", "input")
        if type_ == "value":
            assert io == "input", (k, io)
        if type_ == "cell":
            assert io in ("input", "output"), (k, io)
        default = v.get("default")
        try:
            json.dumps(default)
        except:
            raise ValueError((k, default)) from None
        result[k] = {
            "type": type_,
            "io": io,
            "default": default
        }
    return result 

def get_library(path):
    graph, zip, constructor, params = _libraries[path]
    lib = Library(path, graph, zip, constructor, params)
    return lib

def set_library(path, graph, zip, constructor, params):
    validated_params = validate_params(params)
    _libraries[path] = graph, zip, constructor, validated_params

class LibraryContainer:
    def __init__(self, path):
        if isinstance(path, str):
            path = (path,)
        elif isinstance(path, (list, tuple)):
            path = tuple(path)
        else:
            raise TypeError(type(path))
        self._path = path
    def __getattr__(self, attr):
        path = self._path + (attr,)
        try:
            return get_library(path)
        except KeyError:
            return LibraryContainer(path)
    def __setattr__(self, attr, value): 
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        libctx = value
        if not isinstance(libctx, Context):
            raise TypeError(type(libctx))
        path = self._path + (attr,)        
        graph = libctx.get_graph()
        zip = libctx.get_zip()
        set_library(path, graph, zip, None, None)

class Library:
    def __init__(self, path, graph, zip, constructor=None, params=None):
        self._path = path
        self._graph = graph
        self._zip = zip
        self._constructor = constructor
        self._params = params

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        if attr == "ctx":
            self._graph = ctx.get_graph()
            self._zip = ctx.get_zip()            
            set_library(
                self._path, 
                self._graph, self._zip,
                self._constructor, self._params
            )
        elif attr == "constructor":
            constructor = value
            if inspect.isfunction(constructor):
                code = inspect.getsource(constructor)
                code = strip_source(code)
                constructor = code
            self._constructor = constructor
            set_library(
                self._path, 
                self._graph, self._zip,
                self._constructor, self._params
            )
            return
        elif attr == "params":
            params = value
            if not isinstance(params, dict):
                raise TypeError(type(value))
            self._params = params
            set_library(
                self._path, 
                self._graph, self._zip,
                self._constructor, self._params
            )
            return
        else:
            raise AttributeError(attr)

    def _params_getter(self):
        return self._params

    def _params_setter(self, value):
        self._params = value

    def __getattr__(self, attr):
        if attr == "ctx":
            graph = self._graph
            if graph is None:
                raise AttributeError(attr)
            ctx = Context()
            ctx._weak = True
            ctx.set_graph(graph)
            ctx.add_zip(self._zip)
            ctx.equilibrate()
            return ctx
        elif attr == "constructor":
            return self._constructor
        elif attr == "params":
            backend = DefaultBackend(
                plain=True,
                data_getter=self._params_getter,
                data_setter=self._params_setter
            )
            monitor = Monitor(backend)
            return MixedDict(monitor, ())
        else:
            raise AttributeError(attr)
    
    def include(self, ctx, full_path=False):
        assert self.constructor is not None
        assert self.params is not None
        lib = {
            "graph": self._graph,
            "constructor":self._constructor, 
            "params": self._params,
            "language": "python",
            "api": "pyseamless"
        }
        path = self._path if full_path else self._path[-1:]
        IncludedLibrary(ctx, path, **lib)   # to validate the arguments
        s = json.dumps(lib)
        lib = json.loads(s)
        ctx.add_zip(self._zip)
        ctx._graph.lib[path] = lib

    def include_zip(self, ctx):
        ctx.add_zip(self._zip)

    def __dir__(self):
        dirs = list(super().__dir__())
        for attr in self.__dict__:
            if attr.startswith("_") and attr in dirs:
                dirs.remove(attr)
        dirs += ["ctx", "constructor", "params"]
        return dirs

from .include import IncludedLibrary
from ..Context import Context
from ...core.utils import strip_source
from ...silk import Silk
from ...mixed import DefaultBackend, Monitor, MixedDict
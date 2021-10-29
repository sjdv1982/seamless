import json, inspect
import textwrap

_libraries = {}

def validate_params(params):
    if params is None:
        return None
    result = {}
    for k, v in params.items():
        assert k not in ("ctx",)
        if isinstance(v, str):
            v = {"type": v}
        type_ = v.get("type", "value")
        assert type_ in ("value", "cell", "celldict", "context", "kwargs"), (k, type_)
        io = v.get("io", "input")
        if type_ in ("value", "context", "kwargs"):
            assert io == "input", (k, io)
        if type_ in ("cell", "celldict"):
            assert io in ("input", "output", "edit"), (k, io)
        default = v.get("default")
        celltype = v.get("celltype")
        must_be_defined = v.get("must_be_defined")
        try:
            json.dumps(default)
        except:
            raise ValueError((k, default)) from None
        result[k] = {
            "type": type_,
            "io": io,
            "default": default
        }
        if must_be_defined is not None:
            if must_be_defined not in (True, False):
                raise ValueError((k, must_be_defined))
            result[k]["must_be_defined"] = must_be_defined
        if celltype is not None:
            result[k]["celltype"] = celltype
    return result

def get_library(path):
    (
        graph, zip, constructor, params, 
        api_schema, constructor_schema
    ) = _libraries[path]
    lib = Library(
        path, graph, zip, constructor, params,
        api_schema=api_schema,
        constructor_schema=constructor_schema
    )
    return lib

def set_library(path, graph, zip, constructor, params,
    *, api_schema, constructor_schema):
    validated_params = validate_params(params)
    _libraries[path] = (
        graph, zip, constructor, validated_params,
        api_schema, constructor_schema
    )

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
        set_library(
            path, graph, zip, None, None,
            api_schema=None, constructor_schema=None
        )

class Library:
    def __init__(self, path, graph, zip, 
        constructor=None, params=None, 
        *,
        api_schema=None, constructor_schema=None
    ):
        self._path = path
        self._graph = graph
        self._zip = zip
        self._constructor = constructor
        self._params = params
        self._api_schema = api_schema
        self._constructor_schema = constructor_schema

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        ok = False
        if attr == "ctx":
            self._graph = value.get_graph()
            self._zip = value.get_zip()
            ok = True
        elif attr == "constructor":
            constructor = value
            if inspect.isfunction(constructor):
                code = inspect.getsource(constructor)
                code = textwrap.dedent(code)
                constructor = code
            self._constructor = constructor
            ok = True
        elif attr == "params":
            params = value
            if isinstance(params, Silk):
                params = params.unsilk
            if not isinstance(params, dict):
                raise TypeError(type(value))
            self._params = params
            ok = True
        elif attr in ("constructor_schema", "api_schema"):
            schema = value
            if isinstance(schema, Silk):
                schema = schema.unsilk
            if not isinstance(schema, dict):
                raise TypeError(type(schema))
            setattr(self, "_" + attr, schema)
            ok = True
        if ok:
            set_library(
                self._path,
                self._graph, self._zip,
                self._constructor, self._params,
                constructor_schema=self._constructor_schema,
                api_schema=self._api_schema
            )
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
            ctx.add_zip(self._zip)
            ctx.set_graph(graph)
            ctx.compute()
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

    def include(self, ctx, full_path=False, add_zip=True):
        assert self.constructor is not None
        assert self.params is not None
        path = self._path if full_path else self._path[-1:]
        lib = {
            "graph": self._graph,
            "path": list(path),
            "constructor": self._constructor,
            "params": self._params,
            "language": "python",
            "api": "pyseamless"
        }
        if self._constructor_schema is not None:
            lib["constructor_schema"] = self._constructor_schema
        if self._api_schema is not None:
            lib["api_schema"] = self._api_schema
        IncludedLibrary(ctx, **lib)   # to validate the arguments
        s = json.dumps(lib)
        lib = json.loads(s)
        if add_zip:
            ctx.add_zip(self._zip)
        ctx._set_lib(path, lib)
        for libdep in self._graph.get("lib", {}):
            libdep_path = tuple(libdep["path"])
            ctx._set_lib(libdep_path, libdep)

    def include_zip(self, ctx):
        ctx.add_zip(self._zip)

    def __dir__(self):
        dirs = list(super().__dir__())
        for attr in self.__dict__:
            if attr.startswith("_") and attr in dirs:
                dirs.remove(attr)
        dirs += ["ctx", "constructor", "params", "api_schema", "constructor_schema"]
        return dirs

from .include import IncludedLibrary
from ..Context import Context
from silk import Silk
from silk.mixed import DefaultBackend, Monitor, MixedDict

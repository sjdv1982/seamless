from copy import deepcopy
from inspect import Signature, Parameter

def get_argument_value(name, value):
    if isinstance(value, Cell):
        if value._get_htf()["constant"]:
            value = value.value
    elif isinstance(value, Base):
        raise TypeError("%s must be value or constant cell, not '%s'" % (name, type(value)))
    return RichValue(value).value

class IncludedLibraryContainer:
    def __init__(self, ctx, path):
        assert isinstance(ctx, Context)
        self._ctx = ctx
        self._path = path
    def __dir__(self):
        ctx = self._ctx
        libs = ctx._get_libs(self._path)
        attrs = set([p[0] for p in libs])
        return attrs
    def __getattr__(self, attr):
        attr2 = (attr,)
        ctx = self._ctx
        libs = ctx._get_libs(self._path)
        if attr2 in libs:
            lib = libs[attr2]            
            return IncludedLibrary(
                ctx=ctx,
                path=self._path + attr2,
                **lib
            )
        attrs = set([p[0] for p in libs])
        if attr in attrs:
            return IncludedLibraryContainer(
                self._ctx,
                self._path + attr2
            )
        else:
            raise AttributeError(attr)

class IncludedLibrary:
    def __init__(self, ctx, path, graph, constructor, params):
        self._ctx = ctx
        self._path = path
        self._graph = graph
        self._constructor = constructor
        self._params = params
        func_parameters = []
        for k, v in params.items():
            func_par = Parameter(k, Parameter.POSITIONAL_OR_KEYWORD)
            func_parameters.append(func_par)
        self._signature = Signature(func_parameters)
        identifier = ".".join(self._path)
        cached_compile(self._constructor, identifier)  # just to validate

    def __call__(self, *args, **kwargs):
        arguments0 = self._signature.bind(*args, **kwargs)
        arguments0.apply_defaults()        
        arguments = {}        
        for argname, argvalue in arguments0.arguments.items():
            par = self._params[argname]
            if par["type"] == "value":
                value = get_argument_value(argname, argvalue)
            else: # par["type"] == "cell":
                if not isinstance(argvalue, Cell):
                    msg = "%s must be Cell, not '%s'"
                    raise TypeError(msg % (argname, type(argvalue)))
                value = argvalue._path
            arguments[argname] = value

        libmacro = LibMacro(self._ctx, libpath=self._path, arguments=arguments)
        return libmacro

from ...core.cached_compile import cached_compile
from .libmacro import LibMacro        
from ..Base import Base
from ..Cell import Cell
from ..Context import Context
from ...silk.Silk import RichValue
from copy import deepcopy
from inspect import Signature, Parameter
from collections import OrderedDict

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
            lib = libs[attr2].copy()
            lib["path"] = self._path + attr2
            return IncludedLibrary(
                ctx=ctx,
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
    def __init__(self, ctx, path, graph, constructor, params, **kwargs):
        self._ctx = ctx
        self._path = path
        self._graph = graph
        self._constructor = constructor
        self._params = OrderedDict(params)
        identifier = ".".join(self._path)
        cached_compile(self._constructor, identifier)  # just to validate

    def __call__(self, **kwargs):
        kwargs2 = kwargs.copy()
        params = list(self._params.items())
        for n in range(len(params)):
            k,v = params[n]
            if k in kwargs2:
                continue
            default = v.get("default")
            if default is not None:
                kwargs2[k] = default
        arguments = {}
        for argname, argvalue in kwargs2.items():
            par = self._params[argname]
            arguments[argname] = parse_argument(argname, argvalue, par, parent=self._ctx)

        libinstance = LibInstance(self._ctx, libpath=self._path, arguments=arguments)
        return libinstance

from ...core.cached_compile import cached_compile
from .libinstance import LibInstance
from .argument import parse_argument
from ..Context import Context
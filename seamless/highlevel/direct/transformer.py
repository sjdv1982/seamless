from copy import deepcopy
from functools import update_wrapper
import inspect
from functools import partial
import textwrap
from types import LambdaType

def transformer(func=None, *, local=None, return_transformation=False):
    """Wraps a function in a direct transformer
    Direct transformers can be called as normal functions, but
    the source code of the function and the arguments are converted
    into a Seamless transformation."""
    if func is None:
        return partial(transformer, local=local, return_transformation=return_transformation)
    result = DirectTransformer(func, local=local, return_transformation=return_transformation)
    update_wrapper(result, func)
    return result


def getsource(func):
    from seamless.util import strip_decorators
    from seamless.core.lambdacode import lambdacode

    if isinstance(func, LambdaType) and func.__name__ == "<lambda>":
        code = lambdacode(func)
        if code is None:
            raise ValueError("Cannot extract source code from this lambda")
        return code
    else:
        code = inspect.getsource(func)
        code = textwrap.dedent(code)
        code = strip_decorators(code)
        return code

class DirectTransformer:
    def __init__(self, func, local, return_transformation):
        """Direct transformer.
Direct transformers can be called as normal functions, but
the source code of the function and the arguments are converted
into a Seamless transformation

Parameters:
        
- local. If True, transformations are executed in the local 
            Seamless instance.
        If False, they are delegated to remote job servers.
        If None (default), remote job servers are tried first 
        and local execution is a fallback.

- return_transformation.
        If False, calling the function executes it immediately,
            returning its value.
        If True, it returns a Transformation object.
        Imperative transformations can be queried for their .value
        or .logs. Doing so forces their execution.
        As of Seamless 0.12, forcing one transformation also forces 
            all other transformations. 

Attributes:            

- meta. Accesses all meta-information (including local)

- celltypes. Returns a wrapper where you can set the celltypes
        of the individual transformer pins. 
    The syntax is: Transformer.celltypes.a = "text" 
    (or Transformer.celltypes["a"] = "text") 
    for pin "a".
    
- modules: Returns a wrapper where you can define Python modules
    to be imported into the transformation

- environment    .
"""    
        from seamless.core.protocol.serialize import serialize_sync as serialize
        code = getsource(func)
        codebuf = serialize(code, "python")
        
        signature = inspect.signature(func)
        self._return_transformation = return_transformation
        self._signature = signature
        self._codebuf = codebuf
        self._celltypes = {k: "mixed" for k in signature.parameters}
        self._celltypes["result"] = "mixed"
        self._modules = {}
        self._environment = Environment(self)
        self._environment_state = None

        self._meta = {"transformer_path": ["tf", "tf"], "local": local}
        update_wrapper(self, func)

    @property
    def celltypes(self):
        return CelltypesWrapper(self._celltypes)

    @property
    def modules(self):
        return ModulesWrapper(self._modules)

    @property
    def environment(self) -> "Environment":
        """Computing environment to execute transformations in"""
        return self._environment

    def __call__(self, *args, **kwargs):
        from .Transformation import Transformation, transformation_from_dict
        from ...core.direct.run import run_transformation_dict, direct_transformer_to_transformation_dict, prepare_transformation_dict
        from ...core.cache.database_client import database
        from ...core.cache.buffer_remote import has_readwrite_servers
        from ...core.protocol.get_buffer import get_buffer
        from ...core.protocol.deserialize import deserialize_sync
        from ...core.direct.run import fingertip
        from ...core.direct.module import get_module_definition
        from seamless import CacheMissError
        from seamless.util import is_forked

        if is_forked():
            if not database.active or not has_readwrite_servers():
                raise RuntimeError("Running @transformer inside a transformation requires a Seamless database and buffer servers")

        arguments = self._signature.bind(*args, **kwargs).arguments
        deps = {}
        for argname, arg in arguments.items():
            if isinstance(arg, Transformation):
                deps[argname] = arg

        env = self._environment._to_lowlevel()
        meta = deepcopy(self._meta)
        result_celltype = self._celltypes["result"]
        modules = {}
        for module_name, module in self._modules.items():
            module_definition = get_module_definition(module)
            modules[module_name] = module_definition

        transformation_dict = direct_transformer_to_transformation_dict(
            self._codebuf, meta, self._celltypes, modules, arguments, env
        )
        if self._return_transformation:
            return transformation_from_dict(transformation_dict, result_celltype, upstream_dependencies = deps)
        else:
            for depname, dep in deps.items():
                dep.compute()
                if dep.exception is not None:
                    msg = "Dependency '{}' has an exception: {}"
                    raise RuntimeError(msg.format(depname, dep.exception))
                
            prepare_transformation_dict(transformation_dict)
            result_checksum = run_transformation_dict(transformation_dict, fingertip=False)
            if result_checksum is None:
                raise RuntimeError("Result is empty")
            buf = get_buffer(result_checksum, remote=True)
            if buf is None:
                buf = fingertip(result_checksum)
            if buf is None:
                raise CacheMissError(result_checksum.hex())            
            return deserialize_sync(buf, result_checksum, result_celltype, copy=True)



    @property
    def meta(self):
        return self._meta

    @meta.setter
    def meta(self, meta:dict):
        self._meta[:] = meta

    @property
    def local(self) -> bool | None:
        """Local execution.
If True, transformations are executed in the local Seamless instance.
If False, they are delegated to an assistant.
If None (default), 
an assistant is tried first and local execution is a fallback."""
        return self.meta.get("local")

    @local.setter
    def local(self, value:bool | None):
        self.meta["local"] = value

    @property
    def return_transformation(self) -> bool:
        return self._return_transformation

    @return_transformation.setter
    def return_transformation(self, value:bool):
        self._return_transformation = value

    
class CelltypesWrapper:
    """Wrapper around an imperative transformer's celltypes."""
    def __init__(self, celltypes):
        self._celltypes = celltypes
    def __getattr__(self, attr):
        return self._celltypes[attr]
    def __getitem__(self, key):
        return self._celltypes[key]
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        return self.__setitem__(attr, value)
    def __setitem__(self, key, value):
        from ...core.cell import celltypes
        if key not in self._celltypes:
            raise AttributeError(key)
        pin_celltypes = list(celltypes.keys()) + ["silk"]
        if value not in pin_celltypes:
            raise TypeError(value, pin_celltypes)
        self._celltypes[key] = value
    def __dir__(self):
        return sorted(self._celltypes.keys())
    def __str__(self):
        return str(self._celltypes)
    def __repr__(self):
        return str(self)

class ModulesWrapper:
    """Wrapper around an imperative transformer's imported modules."""
    def __init__(self, modules):
        self._modules = modules
    def __getattr__(self, attr):
        return self._modules[attr]
    def __setattr__(self, attr, value):
        from types import ModuleType
        if attr.startswith("_"):
            return super().__setattr__(attr, value)
        if not isinstance(value, ModuleType):
            raise TypeError(type(value))
        self._modules[attr] = value
    def __dir__(self):
        return sorted(self._modules.keys())
    def __str__(self):
        return str(self._modules)
    def __repr__(self):
        return str(self)
    
from ..Environment import Environment
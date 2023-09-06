def transformer(func, **kwargs):
    """Wraps a function in an imperative transformer
    Imperative transformers can be called as normal functions, but
    the source code of the function and the arguments are converted
    into a Seamless transformation."""
    raise NotImplementedError
    result = DirectTransformer(func, is_async=False, **kwargs)
    update_wrapper(result, func)
    return result


# raise NotImplementedError  # TODO: simplify, only support __call__

class DirectTransformer:
    def __init__(self, func, is_async, **kwargs):
        """Imperative transformer.
Imperative transformers can be called as normal functions, but 
the source code of the function and the arguments are converted
into a Seamless transformation.

The transformer may be asynchronous, which means that calling it
creates a coroutine.

The following properties can be set:
        
- local. If True, transformations are executed in the local 
            Seamless instance.
        If False, they are delegated to remote job servers.
        If None (default), remote job servers are tried first 
        and local execution is a fallback.

- blocking. Only for non-async transformers.
        If True, calling the function executes it immediately,
            returning its value.
        If False, it returns an imperative Transformation object.
        Imperative transformations can be queried for their .value
        or .logs. Doing so forces their execution.
        As of Seamless 0.11, forcing one transformation also forces 
            all other transformations. 

- celltypes. Returns a wrapper where you can set the celltypes
        of the individual transformer pins. 
    The syntax is: Transformer.celltypes.a = "text" 
    (or Transformer.celltypes["a"] = "text") 
    for pin "a"."""
        from ..highlevel.Environment import Environment
        from . import getsource, serialize, calculate_checksum, _get_semantic
        code = getsource(func)
        codebuf = serialize(code, "python")
        code_checksum = calculate_checksum(codebuf)
        semantic_code_checksum = _get_semantic(code, code_checksum)
        
        signature = inspect.signature(func)

        self._semantic_code_checksum = semantic_code_checksum
        self._signature = signature
        self._codebuf = codebuf
        self._code_checksum = code_checksum
        self._is_async = is_async
        self._celltypes = {k: "mixed" for k in signature.parameters}
        self._celltypes["result"] = "mixed"
        self._modules = {}
        self._blocking = True
        self._environment = Environment(self)
        self._environment_state = None

        if "meta" in kwargs:
            self._meta = deepcopy(kwargs["meta"])
        else:
            self._meta = {"transformer_path": ["tf", "tf"]}
        self._kwargs = kwargs
        functools.update_wrapper(self, func)

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
        from .Transformation import Transformation
        from .module import get_module_definition
        from . import run_direct_transformer, run_direct_transformer_async
        from ..core.cache.database_client import database
        from ..core.cache.buffer_remote import has_readwrite_servers
        self._signature.bind(*args, **kwargs)
        if multiprocessing.current_process().name != "MainProcess":
            if self._is_async:
                raise NotImplementedError  # no plans to implement this...
            if not database.active or not has_readwrite_servers():
                #raise NotImplementedError # ALSO requires a buffer write server... unless it is non-local and a assistant is available
                raise RuntimeError("Running @transformer inside a transformation requires a Seamless database and buffer servers")
        runner = run_direct_transformer_async if self._is_async else run_direct_transformer
        if not self._blocking:
            tr = Transformation()
            result_callback = tr._set
        else:
            result_callback = None
        modules = {}
        for module_name, module in self._modules.items():
            module_definition = get_module_definition(module)
            modules[module_name] = module_definition
        result = runner(
            self._semantic_code_checksum,
            self._codebuf,
            self._code_checksum,
            self._signature,
            self._meta,
            self._celltypes,
            modules,
            result_callback,
            args,
            kwargs,
            env=self._environment._to_lowlevel()
        )
        if self._blocking:
            return result
        else:
            return tr

    @property
    def meta(self):
        return self._meta

    @meta.setter
    def meta(self, meta):
        self._meta[:] = meta

    @property
    def local(self):
        return self.meta.get("local")

    @local.setter
    def local(self, value:bool):
        self.meta["local"] = value

    @property
    def blocking(self):
        return self._blocking

    @blocking.setter
    def blocking(self, value:bool):
        if not isinstance(value, bool):
            raise TypeError(value)
        if (not value) and self._is_async:
            raise ValueError("non-blocking is meaningless for a coroutine")
        self._blocking = value

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(type(self), attr):
            return super().__setattr__(attr, value)
        raise AttributeError(attr)
    
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
        from ..core.cell import celltypes
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
    
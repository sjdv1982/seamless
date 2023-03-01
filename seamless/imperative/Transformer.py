"""Imperative transformers"""

import inspect
from copy import deepcopy
import functools
import multiprocessing

class Transformer:
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
        from . import getsource, serialize, calculate_checksum, _get_semantic
        code = getsource(func)
        codebuf = serialize(code, "python")
        code_checksum = calculate_checksum(codebuf)
        semantic_code_checksum = _get_semantic(code, code_checksum)
        signature = inspect.signature(func)

        self.semantic_code_checksum = semantic_code_checksum
        self.signature = signature
        self.codebuf = codebuf
        self.code_checksum = code_checksum
        self.is_async = is_async
        self._celltypes = {k: "mixed" for k in signature.parameters}
        self._celltypes["result"] = "mixed"
        self._blocking = True
        if "meta" in kwargs:
            self.meta = deepcopy(kwargs["meta"])
        else:
            self.meta = {"transformer_path": ["tf", "tf"]}
        self.kwargs = kwargs
        functools.update_wrapper(self, func)

    @property
    def celltypes(self):
        return CelltypesWrapper(self._celltypes)

    def __call__(self, *args, **kwargs):
        from .Transformation import Transformation
        from . import _run_transformer, _run_transformer_async
        from .. import database_sink
        self.signature.bind(*args, **kwargs)
        if multiprocessing.current_process().name != "MainProcess":
            if self.is_async:
                raise NotImplementedError  # no plans to implement this...
            if not database_sink.active:
                raise RuntimeError("Running @transformer inside a transformation requires a Seamless database")
        runner = _run_transformer_async if self.is_async else _run_transformer
        if not self._blocking:
            tr = Transformation()
            result_callback = tr._set
        else:
            result_callback = None
        result = runner(
            self.semantic_code_checksum,
            self.codebuf,
            self.code_checksum,
            self.signature,
            self.meta,
            self._celltypes,
            result_callback,
            args,
            kwargs
        )
        if self._blocking:
            return result
        else:
            return tr

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
        if (not value) and self.is_async:
            raise ValueError("non-blocking is meaningless for a coroutine")
        self._blocking = value

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

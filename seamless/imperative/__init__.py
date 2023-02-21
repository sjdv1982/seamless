import inspect
import textwrap
from types import LambdaType
import ast
import functools
from copy import deepcopy
import multiprocessing
import time

from ..calculate_checksum import calculate_checksum
from ..core.protocol.serialize import serialize_sync as serialize, serialize as serialize_async
from ..core.protocol.deserialize import deserialize_sync as deserialize, deserialize as deserialize_async
from ..core.protocol.get_buffer import get_buffer as _get_buffer
from ..core.lambdacode import lambdacode
from ..core.cache.transformation_cache import transformation_cache, tf_get_buffer, incref_transformation, syntactic_is_semantic, DummyTransformer
from ..core.cache.tempref import temprefmanager
from .. import run_transformation, run_transformation_async

_queued_transformations = []

_sem_code_cache = {}

_parent_process_queue = None
_parent_process_response_queue = None
_has_lock = True

def _set_parent_process_queue(parent_process_queue):
    global _parent_process_queue
    _parent_process_queue = parent_process_queue

def _set_parent_process_response_queue(parent_process_response_queue):
    global _parent_process_response_queue
    _parent_process_response_queue = parent_process_response_queue

def getsource(func):
    from ..util import strip_decorators
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

def cache_buffer(checksum, buf):
   from ..core.cache.buffer_cache import buffer_cache
   buffer_cache.cache_buffer(checksum, buf) 


def get_buffer(checksum):
    #return _get_buffer(checksum, remote=False)
    return _get_buffer(checksum, remote=True)

def _register_transformation_dict(transformation_checksum, transformation_buffer, transformation_dict):
    # This is necessary to support transformation dicts that are not quite the same as their transformation buffers.
    # This happens in case of __meta__, __compilers__ or __languages__ fields in the dict
    # The transformation buffer has them stripped, so that transformations with different __meta__ get the same checksum.
    # See tf_get_buffer source code for details
    # In addition, the buffers in the checksum have now a Seamless refcount and will not be garbage collected.    
    from ..core.cache.buffer_cache import buffer_cache
    result = None
    if transformation_checksum not in transformation_cache.transformations_to_transformers:
        transformation_cache.transformations_to_transformers[transformation_checksum] = []
    if transformation_checksum not in transformation_cache.transformations:
        if transformation_checksum in transformation_cache.transformation_results:
            result_checksum, _ = transformation_cache.transformation_results[transformation_checksum]
            buffer_cache.incref(result_checksum, False)
        incref_transformation(transformation_checksum, transformation_buffer, transformation_dict)
        result = DummyTransformer(transformation_checksum)
        transformation_cache.transformations_to_transformers[transformation_checksum].append(result)
    transformation_cache.transformations[transformation_checksum] = transformation_dict
    return result

def run_transformation_dict(transformation_dict, result_callback=None):
    from .. import database_sink
    # TODO: add type annotation and all kinds of validation...
    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    increfed =_register_transformation_dict(transformation, transformation_buffer, transformation_dict)    
    if multiprocessing.current_process().name != "MainProcess":
        assert database_sink.active
        result_checksum, prelim = transformation_cache._get_transformation_result(transformation)
        if result_checksum is not None and not prelim:
            metalike, syntactic_cache = None, []
        else: 
            assert _parent_process_queue is not None
            metalike = {}
            for k in ("__compilers__", "__languages__", "__meta__"):
                if k in transformation_dict:
                    metalike[k] = transformation_dict[k]
            meta = metalike.get("__meta__")
            if meta is None:
                meta = {}
                metalike["__meta__"] = meta
            if meta.get("local") is None:
                # local (fat) by default
                meta["local"] = True
            syntactic_cache = []
            for k in transformation_dict:
                if k.startswith("__"):
                    continue
                celltype, subcelltype, sem_checksum = transformation_dict[k]
                if syntactic_is_semantic(celltype, subcelltype):
                    continue
                semkey = (bytes.fromhex(sem_checksum), celltype, subcelltype)
                syn_checksum = transformation_cache.semantic_to_syntactic_checksums[semkey][0]
                syn_buffer = get_buffer(syn_checksum)
                assert syn_buffer is not None            
                syntactic_cache.append((celltype, subcelltype, syn_buffer))
    else:
        metalike, syntactic_cache = None, []
    
    output_celltype = transformation_dict["__output__"][1]
    _queued_transformations.append((result_callback, transformation.hex(), transformation_dict, metalike, syntactic_cache, increfed, output_celltype))
    if result_callback is None:
        return _wait()[0]
    else:
        return

async def run_transformation_dict_async(transformation_dict):
    # TODO: add type annotation and all kinds of validation...
    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    increfed = _register_transformation_dict(transformation, transformation_buffer, transformation_dict)
    try:
        result_checksum = await run_transformation_async(transformation)
        celltype = transformation_dict["__output__"][1]
        result_buffer = get_buffer(result_checksum) # does this raise CacheMissError?
        return await deserialize_async(result_buffer, result_checksum, celltype, copy=True)
    finally:
        # For some reason, the logic here is different than for the sync version (see _wait())
        if increfed and increfed in transformation_cache.transformations_to_transformers.get(transformation, []):            
            transformation_cache.decref_transformation(transformation_dict, increfed)
        temprefmanager.purge_group('imperative')

def _parse_arguments(signature, args, kwargs):
    if signature is None:
        assert not args
        arguments = kwargs
    else:
        arguments = signature.bind(*args, **kwargs).arguments
    return arguments

def _run_transformer(semantic_code_checksum, codebuf, code_checksum, signature, meta, celltypes, result_callback, args, kwargs):
    # TODO: celltype support for args / return
    from .. import database_sink
    arguments = _parse_arguments(signature, args, kwargs)
    transformation_dict = {
        "__output__": ("result", "mixed", None), 
        "__language__": "python"
    }
    if meta:
        transformation_dict["__meta__"] = meta
    transformation_dict["code"] = ("python", "transformer", semantic_code_checksum)
    for argname, arg in arguments.items():
        buf = serialize(arg, "mixed")
        checksum = calculate_checksum(buf, hex=False)
        cache_buffer(checksum, buf)
        transformation_dict[argname] = ("mixed", None, checksum.hex())
    cache_buffer(code_checksum, codebuf)
    # Code below could be moved, see transformation.py syntactic_cache
    # (same code as _run_transformer_async)
    semantic_code_checksum2 = bytes.fromhex(semantic_code_checksum)
    semcode = _sem_code_cache[semantic_code_checksum]
    cache_buffer(semantic_code_checksum2, semcode)
    database_sink.set_buffer(semantic_code_checksum2, semcode, False)
    database_sink.set_buffer(code_checksum, codebuf, False)
    semkey = (semantic_code_checksum2, "python", "transformer")
    database_sink.sem2syn(semkey, [code_checksum])
    return run_transformation_dict(transformation_dict, result_callback)

async def _run_transformer_async(semantic_code_checksum,  codebuf, code_checksum, signature, meta, celltypes, result_callback, args, kwargs):
    from .. import database_sink
    assert result_callback is None  # meaningless for async
    arguments = signature.bind(*args, **kwargs).arguments
    transformation_dict = {
        "__output__": ("result", "mixed", None), 
        "__language__": "python"
    }
    if meta:
        transformation_dict["__meta__"] = meta
    transformation_dict["code"] = ("python", "transformer", semantic_code_checksum)
    for argname, arg in arguments.items():
        buf = await serialize_async(arg, "mixed")
        checksum = calculate_checksum(buf, hex=False)
        cache_buffer(checksum, buf)
        transformation_dict[argname] = ("mixed", None, checksum.hex())
    cache_buffer(code_checksum, codebuf)
    # Code below could be moved, see transformation.py syntactic_cache
    # (same code as _run_transformer)
    semantic_code_checksum2 = bytes.fromhex(semantic_code_checksum)
    semcode = _sem_code_cache[semantic_code_checksum]
    cache_buffer(semantic_code_checksum2, semcode)
    database_sink.set_buffer(semantic_code_checksum2, semcode, False)
    database_sink.set_buffer(code_checksum, codebuf, False)
    semkey = (semantic_code_checksum2, "python", "transformer")
    database_sink.sem2syn(semkey, [code_checksum])
    return await run_transformation_dict_async(transformation_dict)

def _get_semantic(code, code_checksum):
    tree = ast.parse(code, filename="<None>")
    semcode = ast.dump(tree).encode()
    semantic_code_checksum = calculate_checksum(semcode, hex=True)
    _sem_code_cache[semantic_code_checksum] = semcode
    key = (bytes.fromhex(semantic_code_checksum), "python", "transformer")
    transformation_cache.semantic_to_syntactic_checksums[key] = [code_checksum]
    return semantic_code_checksum

class Transformation:
    def __init__(self):
        self._value = None
        self._logs = None

    def _set(self, value, logs):
        self._value = value
        self._logs = logs

    @property
    def value(self):
        if self._value is None:
            _wait()
        return self._value
        
    @property
    def logs(self):
        if self._value is None:
            _wait()
        return self._logs

class Transformer:
    def __init__(self, func, is_async, **kwargs):
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
        self._celltypes = {}
        self._blocking = True
        if "meta" in kwargs:
            self.meta = deepcopy(kwargs["meta"])
        else:
            #self.meta = {}
            self.meta = {"transformer_path": ["tf", "tf"]}
        self.kwargs = kwargs
        functools.update_wrapper(self, func)

    def __call__(self, *args, **kwargs):
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
        return self.meta.get("local", False)

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

def transformer(func, **kwargs):
    return Transformer(func, is_async=False, **kwargs)

def transformer_async(func, **kwargs):
    return Transformer(func, is_async=True, **kwargs)

def _wait():
    global _queued_transformations
    global _has_lock
    if not _queued_transformations:
        return None
    results = []
    queued_transformations = _queued_transformations.copy()
    _queued_transformations.clear()
    had_lock = _has_lock
    # NOTE: for future optimization, one could run transformations in batch mode.
    #   one batch for the parent process queue, and one batch for local run_transformation
    forked = (multiprocessing.current_process().name != "MainProcess")
    if forked and _has_lock:        
        _parent_process_queue.put((5, "release lock"))
        _has_lock = False
    for callback, transformation, transformation_dict, metalike, syntactic_cache, increfed, output_celltype in queued_transformations:
        try:
            if forked:
                _parent_process_queue.put((7, (transformation, metalike, syntactic_cache)))
                result_checksum, logs = _parent_process_response_queue.get()
            else:
                result_checksum = run_transformation(transformation)
                logs = None
                if result_checksum is not None:
                    tf_checksum = bytes.fromhex(transformation)
                    logs = transformation_cache.transformation_logs.get(tf_checksum)
        finally:
            # For some reason, the logic here is different than for the async version
            # (see run_transformation_dict_async)
            temprefmanager.purge_group('imperative')
            if increfed and bytes.fromhex(transformation) in transformation_cache.transformations:
                transformation_cache.decref_transformation(transformation_dict, increfed)
            temprefmanager.purge_group('imperative')
            if forked and had_lock and not _has_lock:
                _parent_process_queue.put((6, "acquire lock"))
                _has_lock = True

        result_buffer = get_buffer(result_checksum) # does this raise CacheMissError?
        result = deserialize(result_buffer, result_checksum, output_celltype, copy=True)
        if callback is not None:
            callback(result, logs)
        else:
            # in blocking mode, results are discarded
            # TODO? we could extract stdout/stderr from them?
            results.append(result)
    if not results:
        return None
    return results

def _cleanup():
    """is registered atexit by seamless.core, because it must run first"""
    for _, transformation, transformation_dict, _, _, increfed, _ in _queued_transformations:
        # For some reason, the logic here is different than for the async version
        # (see run_transformation_dict_async)
        if increfed and bytes.fromhex(transformation) in transformation_cache.transformations:
            transformation_cache.decref_transformation(transformation_dict, increfed)


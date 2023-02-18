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
from .. import run_transformation, run_transformation_async

_sem_code_cache = {}

_parent_process_queue = None
_parent_process_response_queue = None


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

def run_transformation_dict(transformation_dict):
    from .. import database_sink
    # TODO: add type annotation and all kinds of validation...
    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    increfed =_register_transformation_dict(transformation, transformation_buffer, transformation_dict)    
    try:
        if multiprocessing.current_process().name != "MainProcess":
            assert database_sink.active
            result_checksum, prelim = transformation_cache._get_transformation_result(transformation)
            if result_checksum is not None and not prelim:
                pass
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
                _parent_process_queue.put((6, (transformation.hex(), metalike, syntactic_cache)))
                # TODO: release lock if blocking
                # TODO: non-blocking
                # TODO: identifier for message (for non-blocking)
                result_checksum = _parent_process_response_queue.get()
                # TODO: acquire lock message (analogous to release lock)
                '''
                while 1:
                    result_checksum, prelim = transformation_cache._get_transformation_result(transformation)
                    if result_checksum is not None and not prelim:
                        breakdecref
                    time.sleep(0.5)
                '''
        else:
            result_checksum = run_transformation(transformation)
    finally:
        if increfed and increfed in transformation_cache.transformations_to_transformers.get(transformation, []):            
            transformation_cache.decref_transformation(transformation_dict, increfed)

    celltype = transformation_dict["__output__"][1]
    result_buffer = get_buffer(result_checksum) # does this raise CacheMissError?
    return deserialize(result_buffer, result_checksum, celltype, copy=True)

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
        if increfed and increfed in transformation_cache.transformations_to_transformers.get(transformation, []):            
            transformation_cache.decref_transformation(transformation_dict, increfed)

def _run_transformer(semantic_code_checksum, codebuf, code_checksum, signature, meta, *args, **kwargs):
    # TODO: support *args (makefun)
    # TODO: celltype support for args / return
    from .. import database_sink
    arguments = signature.bind(*args, **kwargs).arguments
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
    return run_transformation_dict(transformation_dict)

async def _run_transformer_async(semantic_code_checksum,  codebuf, code_checksum, signature, meta, *args, **kwargs):
    # TODO: support *args (makefun)
    # TODO: celltype support for args / return
    from .. import database_sink
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

class Transformer:
    def __init__(self, func, is_async, **kwargs):
        code = getsource(func)
        codebuf = serialize(code, "python")
        code_checksum = calculate_checksum(codebuf)
        tree = ast.parse(code, filename="<None>")
        semcode = ast.dump(tree).encode()
        semantic_code_checksum = calculate_checksum(semcode, hex=True)
        _sem_code_cache[semantic_code_checksum] = semcode
        key = (bytes.fromhex(semantic_code_checksum), "python", "transformer")
        transformation_cache.semantic_to_syntactic_checksums[key] = [code_checksum]
        signature = inspect.signature(func)

        self.semantic_code_checksum = semantic_code_checksum
        self.signature = signature
        self.codebuf = codebuf
        self.code_checksum = code_checksum
        self.is_async = is_async
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
                raise NotImplementedError
            if not database_sink.active:
                raise RuntimeError("Running @transformer inside a transformation requires a Seamless database")
        runner = _run_transformer_async if self.is_async else _run_transformer
        return runner(
            self.semantic_code_checksum,
            self.codebuf,
            self.code_checksum,
            self.signature,
            self.meta,
            *args,
            **kwargs
        )

    @property
    def local(self):
        return self.meta.get("local", False)

    @local.setter
    def local(self, value:bool):
        self.meta["local"] = value

def transformer(func, **kwargs):
    return Transformer(func, is_async=False, **kwargs)

def transformer_async(func, **kwargs):
    return Transformer(func, is_async=True, **kwargs)
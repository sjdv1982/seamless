import inspect
import textwrap
from types import LambdaType
import ast
import functools

from ..calculate_checksum import calculate_checksum
from ..core.protocol.serialize import serialize_sync as serialize, serialize as serialize_async
from ..core.protocol.deserialize import deserialize_sync as deserialize, deserialize as deserialize_async
from ..core.protocol.get_buffer import get_buffer as _get_buffer
from ..core.lambdacode import lambdacode
from ..core.cache.transformation_cache import transformation_cache
from .. import run_transformation, run_transformation_async

_sem_code_cache = {}

def getsource(func):
    if isinstance(func, LambdaType) and func.__name__ == "<lambda>":
        code = lambdacode(func)
        if code is None:
            raise ValueError("Cannot extract source code from this lambda")
        return code
    else:
        code0 = inspect.getsource(func)
        code0 = textwrap.dedent(code0)
        code0 = code0.splitlines()
        for lnr, l in enumerate(code0):
            if l.startswith("@"):
                continue
            return "\n".join(code0[lnr:])

def cache_buffer(checksum, buf):
   from ..core.cache.buffer_cache import buffer_cache
   buffer_cache.cache_buffer(checksum, buf) 

def get_buffer(checksum):
    return _get_buffer(checksum, remote=False)

def run_transformation_dict(transformation_dict):
    # TODO: add type annotation and all kinds of validation...
    transformation_buffer = serialize(transformation_dict, "plain")
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    result_checksum = run_transformation(transformation)
    celltype = transformation_dict["__output__"][1]
    result_buffer = get_buffer(result_checksum) # does this raise CacheMissError?
    return deserialize(result_buffer, result_checksum, celltype, copy=True)

async def run_transformation_dict_async(transformation_dict):
    # TODO: add type annotation and all kinds of validation...
    transformation_buffer = await serialize_async(transformation_dict, "plain")
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    result_checksum = await run_transformation_async(transformation)
    celltype = transformation_dict["__output__"][1]
    result_buffer = get_buffer(result_checksum) # does this raise CacheMissError?
    return await deserialize_async(result_buffer, result_checksum, celltype, copy=True)

def _run_transformer(transformer_code_checksum,  codebuf, code_checksum, signature, *args, **kwargs):
    # TODO: support *args (makefun)
    # TODO: celltype support for args / return
    arguments = signature.bind(*args, **kwargs).arguments
    transformation_dict = {
        "__output__": ("result", "mixed", None), 
        "__language__": "python"
    }
    transformation_dict["code"] = ("python", "transformer", transformer_code_checksum)
    for argname, arg in arguments.items():
        buf = serialize(arg, "mixed")
        checksum = calculate_checksum(buf, hex=False)
        cache_buffer(checksum, buf)
        transformation_dict[argname] = ("mixed", None, checksum.hex())
    cache_buffer(code_checksum, codebuf)
    cache_buffer(bytes.fromhex(transformer_code_checksum), _sem_code_cache[transformer_code_checksum])
    return run_transformation_dict(transformation_dict)

async def _run_transformer_async(transformer_code_checksum,  codebuf, code_checksum, signature, *args, **kwargs):
    # TODO: support *args (makefun)
    # TODO: celltype support for args / return
    arguments = signature.bind(*args, **kwargs).arguments
    transformation_dict = {
        "__output__": ("result", "mixed", None), 
        "__language__": "python"
    }
    transformation_dict["code"] = ("python", "transformer", transformer_code_checksum)
    for argname, arg in arguments.items():
        buf = await serialize_async(arg, "mixed")
        checksum = calculate_checksum(buf, hex=False)
        cache_buffer(checksum, buf)
        transformation_dict[argname] = ("mixed", None, checksum.hex())
    cache_buffer(code_checksum, codebuf)
    cache_buffer(bytes.fromhex(transformer_code_checksum), _sem_code_cache[transformer_code_checksum])
    return await run_transformation_dict_async(transformation_dict)

def transformer(func):
    # TODO: extra args (?)    
    code = getsource(func)
    codebuf = serialize(code, "python")
    code_checksum = calculate_checksum(codebuf)
    tree = ast.parse(code, filename="<None>")
    semcode = ast.dump(tree).encode()
    checksum = calculate_checksum(semcode, hex=True)
    _sem_code_cache[checksum] = semcode
    key = (bytes.fromhex(checksum), "python", "transformer")
    transformation_cache.semantic_to_syntactic_checksums[key] = [code_checksum]
    signature = inspect.signature(func)
    #wrapped docstring
    return functools.partial(_run_transformer, checksum, codebuf, code_checksum, signature)

def transformer_async(func):
    # TODO: extra args (?)    
    code = getsource(func)
    codebuf = serialize(code, "python")
    code_checksum = calculate_checksum(codebuf)
    tree = ast.parse(code, filename="<None>")
    semcode = ast.dump(tree).encode()
    checksum = calculate_checksum(semcode, hex=True)
    _sem_code_cache[checksum] = semcode
    key = (bytes.fromhex(checksum), "python", "transformer")
    transformation_cache.semantic_to_syntactic_checksums[key] = [code_checksum]
    signature = inspect.signature(func)
    return functools.partial(_run_transformer_async, checksum, codebuf, code_checksum, signature)
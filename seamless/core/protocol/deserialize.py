import asyncio
from copy import deepcopy
import json
from ast import literal_eval
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from ...mixed.io import deserialize as mixed_deserialize

from ...pylru import lrucache

deserialize_cache = lrucache(100)

def _deserialize(buffer, checksum, celltype):
    if celltype in text_types2:
        s = buffer.decode()
        assert s.endswith("\n")
        value = s[:-1]
    elif celltype == "plain":
        value, storage = mixed_deserialize(buffer)
        if storage != "pure-plain":
            raise TypeError
    elif celltype == "binary":
        value, storage = mixed_deserialize(buffer)
        if storage != "pure-binary":
            raise TypeError
    elif celltype == "mixed":
        value, _ = mixed_deserialize(buffer)
    elif celltype == "bytes":
        value = buffer
    elif celltype == "str":
        s = buffer.decode()
        assert s.endswith("\n")
        try:
            value = json.loads(s)
        except json.JSONDecodeError:            
            raise ValueError(s) from None
        if not isinstance(value, str):
            raise ValueError(value)
    elif celltype == "int":
        s = buffer.decode()
        assert s.endswith("\n")
        value = literal_eval(s)
        if isinstance(value, (float, bool)):
            value = int(value)
        if not isinstance(value, int):
            raise ValueError(value)
    elif celltype == "float":
        s = buffer.decode()
        assert s.endswith("\n")
        value = literal_eval(s)
        if isinstance(value, (int, bool)):
            value = float(value)        
        if not isinstance(value, float):
            raise ValueError(value)
    elif celltype == "bool":
        s = buffer.decode()
        assert s.endswith("\n")
        value = literal_eval(s)        
        if not isinstance(value, bool):
            raise ValueError(value)
    else:
        raise TypeError(celltype)
    
    return value


async def deserialize(buffer, checksum, celltype, copy):
    """Deserializes a buffer into a value
    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed in a subprocess
     (and copy is irrelevant)."""
    if buffer is None:
        return None
    value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            newvalue = deepcopy(value)
            id_newvalue = id(newvalue)
            serialize_cache[id_newvalue, celltype] = buffer, newvalue
            return newvalue
        else:
            return value
            
    # ProcessPool is too slow, but ThreadPool works
    if len(buffer) > 1000000:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            value = await loop.run_in_executor(
                executor,
                _deserialize,
                buffer, checksum, celltype
            )
    else:
        value = _deserialize(buffer, checksum, celltype)
    if celltype not in text_types2:
        deserialize_cache[checksum, celltype] = value
    evaluation_cache_1.add((checksum, celltype))
    id_value = id(value)
    serialize_cache[id_value, celltype] = buffer, value
    return value

def deserialize_sync(buffer, checksum, celltype, copy):
    """Deserializes a buffer into a value
    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed 
    (and copy is irrelevant)."""
    if buffer is None:
        return None
    value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            newvalue = deepcopy(value)
            id_newvalue = id(newvalue)
            serialize_cache[id_newvalue, celltype] = buffer, newvalue
            return newvalue
        else:
            return value

    value = _deserialize(buffer, checksum, celltype)
    if celltype not in text_types2:
        deserialize_cache[checksum, celltype] = value
    evaluation_cache_1.add((checksum, celltype))
    id_value = id(value)
    serialize_cache[id_value, celltype] = buffer, value
    return value


from .serialize import serialize_cache
from .evaluate import evaluation_cache_1
from ..cell import text_types2
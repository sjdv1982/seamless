import asyncio
import copy
import json
from concurrent.futures import ProcessPoolExecutor
from ...mixed.io import deserialize as mixed_deserialize

from ...pylru import lrucache

deserialize_cache = lrucache(100)

text_types = (
    "text", "python", "ipython", "cson", "yaml",
)

def _deserialize(buffer, checksum, celltype):
    if celltype in text_types:
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
        value = json.loads(s)
        if not isinstance(value, str):
            raise ValueError
    elif celltype == "int":
        s = buffer.decode()
        assert s.endswith("\n")
        value = json.loads(s)
        if isinstance(value, (float, bool)):
            value = int(value)
        if not isinstance(value, int):
            raise ValueError
    elif celltype == "float":
        s = buffer.decode()
        assert s.endswith("\n")
        value = json.loads(s)
        if isinstance(value, (int, bool)):
            value = float(value)        
        if not isinstance(value, float):
            raise ValueError
    elif celltype == "bool":
        s = buffer.decode()
        assert s.endswith("\n")
        value = json.loads(s)
        if not isinstance(value, bool):
            raise ValueError
    else:
        raise TypeError(celltype)
    
    return value


async def deserialize(buffer, checksum, celltype, copy):
    """Deserializes a buffer into a value
    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed in a subprocess
     (and copy is irrelevant)."""
    value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            newvalue = deepcopy.copy(value)
            serialize_cache[id(newvalue), celltype] = buffer
            return newvalue
        else:
            return value
    
    loop = asyncio.get_event_loop()            
    with ProcessPoolExecutor() as executor:
        value = await loop.run_in_executor(
            executor,
            _deserialize,
            buffer, checksum, celltype
        )

    if celltype not in text_types:
        deserialize_cache[checksum, celltype] = value
    evaluation_cache_1.add((checksum, celltype))
    serialize_cache[id(value), celltype] = buffer
    return value

from .serialize import serialize_cache
from .evaluate import evaluation_cache_1
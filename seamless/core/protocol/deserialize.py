import asyncio
import copy
from concurrent.futures import ProcessPoolExecutor

from ...pylru import lrucache

deserialize_cache = lrucache(100)

def _deserialize(buffer, checksum, celltype, copy):
    if celltype != "text": raise NotImplementedError #livegraph branch
    value = buffer
    
    #print("DESERIALIZE", buffer, checksum, value)
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
            buffer, checksum, celltype, copy
        )

    deserialize_cache[checksum, celltype] = value
    serialize_cache[id(value), celltype] = buffer
    return value

from .serialize import serialize_cache    
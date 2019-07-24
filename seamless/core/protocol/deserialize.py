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
    value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            return deepcopy.copy(value)
        else:
            return value
    
    loop = asyncio.get_event_loop()            
    with ProcessPoolExecutor() as executor:
        value = await loop.run_in_executor(
            executor,
            _deserialize,
            buffer, checksum, celltype, copy
        )

    deserialize_cache[(checksum, celltype)] = value
    return value
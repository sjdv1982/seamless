import asyncio
from concurrent.futures import ProcessPoolExecutor

from ...pylru import lrucache

serialize_cache = lrucache(100)

def _serialize(value, celltype):
    if celltype != "text": raise NotImplementedError #livegraph branch
    buffer = value
    
    #print("SERIALIZE", value, buffer)
    return buffer

async def serialize(value, celltype):
    #print("SERIALIZE?", value)
    idvalue = id(value) 
    buffer = serialize_cache.get(idvalue)
    if buffer is not None:
        return buffer

    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        buffer = await loop.run_in_executor(
            executor,
            _serialize,
            value, celltype
        )

    serialize_cache[idvalue] = buffer
    return buffer
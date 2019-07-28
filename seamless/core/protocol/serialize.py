import asyncio
from concurrent.futures import ProcessPoolExecutor

from ...pylru import lrucache

serialize_cache = lrucache(100)

def _serialize(value, celltype):
    if celltype == "text":
        if isinstance(value, bytes):
            buffer = value
        else:
            buffer = str(value).encode()
    elif celltype == "bytes":
        try:
            buffer = value.tobytes()
            return buffer
        except:
            pass
        buffer = str(value).encode()
    elif celltype == "binary":
        if isinstance(value, bytes):
            buffer = value
        else:
            value = np.array(value)
            buffer = value.tobytes()
    else:
        raise NotImplementedError # livegraph branch
    return buffer


async def serialize(value, celltype):
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
import asyncio
import json
from concurrent.futures import ProcessPoolExecutor

from ...pylru import lrucache

from ...mixed.io import serialize as mixed_serialize

serialize_cache = lrucache(100)

text_types = (
    "text", "python", "ipython", "cson", "yaml",
    "str", "int", "float", "bool",
)

def _serialize(value, celltype):
    if celltype in text_types:
        if isinstance(value, bytes):
            value = value.decode()
        if celltype == "int":
            value = int(value)
        elif celltype == "float":
            value = float(value)
        elif celltype == "bool":
            value = bool(value)
        buffer = (str(value).rstrip("\n")+"\n").encode()
    elif celltype == "plain":
        txt = json.dumps(value, sort_keys=True, indent=2)
        buffer = (txt + "\n").encode()
    elif celltype == "mixed":
        buffer = mixed_serialize(value)
    elif celltype == "binary":
        if isinstance(value, bytes):
            buffer = value
        else:
            value = np.array(value)
            buffer = value.tobytes()
    elif celltype == "bytes":
        try:
            buffer = value.tobytes()
            return buffer
        except Exception:
            pass
        buffer = (str(value).rstrip("\n")+"\n").encode()
    else:
        raise TypeError(celltype)
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

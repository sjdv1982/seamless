import asyncio
import json
import weakref
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from ...pylru import lrucache

from ...mixed.io import serialize as mixed_serialize

# serialize_cache: maps id(value),celltype to (buffer, value). 
# Need to store (a ref to) value, 
#  because id(value) is only unique while value does not die!!!
serialize_cache = lrucache(100)


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

async def serialize(value, celltype, use_cache=True):
    assert value is not None
    if use_cache:
        id_value = id(value) 
        buffer, _ = serialize_cache.get((id_value, celltype), (None, None))
        if buffer is not None:
            return buffer
    
    """
    # what can we do to make this async??
    # ThreadPool doesn't work, and ProcessPool is slow
    # (seems to make a copy of the Python structure)
    
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        buffer = await loop.run_in_executor(
            executor,
            _serialize,
            value, celltype
        )
    return buffer
    """
    
    buffer = _serialize(value, celltype)  ### for now...
    if use_cache:
        serialize_cache[id_value, celltype] = buffer, value
    return buffer

def serialize_sync(value, celltype, use_cache=True):
    if use_cache:
        id_value = id(value) 
        buffer, _ = serialize_cache.get((id_value, celltype), (None, None))
        if buffer is not None:
            return buffer
    
    buffer = _serialize(value, celltype)  ### for now...
    if use_cache:
        serialize_cache[id_value, celltype] = buffer, value
    return buffer

from ..cell import text_types


import asyncio
import json
import weakref
import numpy as np
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from seamless.util import lrucache2

from silk.mixed.io import serialize as mixed_serialize
from silk.Silk import Silk

# serialize_cache: maps id(value),celltype to (buffer, value).
# Need to store (a ref to) value,
#  because id(value) is only unique while value does not die!!!
serialize_cache = lrucache2(10)

import logging
logger = logging.getLogger(__name__)

def _serialize(value, celltype):
    from seamless.buffer.json import json_dumps
    if celltype == "str":
        if not isinstance(value, bool):
            value = str(value)
        buffer = json_dumps(value, as_bytes=True) + b"\n"
    elif celltype in text_types:
        if isinstance(value, bytes):
            value = value.decode()
        if celltype in ("int", "float", "bool"):
            if celltype == "int":
                value = int(value)
            elif celltype == "float":
                value = float(value)
            elif celltype == "bool":
                value = bool(value)
            buffer = json_dumps(value, as_bytes=True) + b"\n"
        else:
            buffer = (str(value).rstrip("\n")+"\n").encode()
    elif celltype == "plain":
        buffer = json_dumps(value, as_bytes=True) + b"\n"
    elif celltype == "mixed":
        if isinstance(value, Silk):
            value = value.unsilk
        buffer = mixed_serialize(value)
    elif celltype == "binary":
        if isinstance(value, bytes):
            buffer = value
        else:
            value = np.array(value)
            buffer = mixed_serialize(value)
    elif celltype == "bytes":
        buffer = None
        if isinstance(value, bytes):
            buffer = value
        if buffer is None:
            try:
                buffer = value.tobytes()
            except Exception:
                pass
        if buffer is None:
            buffer = (str(value).rstrip("\n")).encode()
    elif celltype == "checksum":
        buffer = json_dumps(value, as_bytes=True) + b"\n"
    else:
        raise TypeError(celltype)
    logger.debug("SERIALIZE: buffer of length {}".format(len(buffer)))
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
    """This function can be executed if the asyncio event loop is already running"""
    if use_cache:
        id_value = id(value)
        buffer, _ = serialize_cache.get((id_value, celltype), (None, None))
        if buffer is not None:
            return buffer

    buffer = _serialize(value, celltype)  ### for now...
    if use_cache:
        serialize_cache[id_value, celltype] = buffer, value
    return buffer

from .cell import text_types
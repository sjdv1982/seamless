import asyncio
from copy import deepcopy
import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from silk.mixed.io import deserialize as mixed_deserialize
import builtins

from .calculate_checksum import lrucache2

import logging
logger = logging.getLogger("seamless")

deserialize_cache = lrucache2(10)

def _deserialize(buffer, checksum, celltype):
    if celltype == "silk":
        celltype = "mixed"
    assert isinstance(checksum, bytes), type(checksum)
    logger.debug("DESERIALIZE: buffer of length {}, checksum {}".format(len(buffer), checksum.hex()))
    if celltype in text_types2:
        s = buffer.decode()
        value = s.rstrip("\n")
        validate_text_celltype(value, checksum, celltype)
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
    elif celltype in ("str", "int", "float", "bool"):
        s = buffer.decode()
        s = s.rstrip("\n")
        try:
            value = json.loads(s)
        except json.JSONDecodeError:
            raise ValueError from None
        if not isinstance(value, getattr(builtins, celltype)):
            value = getattr(builtins, celltype)(value)
    elif celltype == "checksum":
        try:
            value = buffer.decode()
            validate_checksum(value)
        except (ValueError, UnicodeDecodeError):
            value, storage = mixed_deserialize(buffer)
            if storage != "pure-plain":
                raise TypeError
            validate_checksum(value)
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
    ###
    copy = True # Apparently, sometimes the promise of not modifying the value is violated... for now, enforce a copy
    ###
    if value is not None:
        if copy:
            newvalue = deepcopy(value)
            return newvalue
        else:
            return value


    # ProcessPool is too slow, but ThreadPool works... do experiment with later
    if 0:
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
        if copy:
            value = deepcopy(value)
    if not copy:
        id_value = id(value)
        serialize_cache[id_value, celltype] = buffer, value
    return value

def deserialize_sync(buffer, checksum, celltype, copy):
    """Deserializes a buffer into a value
    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed
    (and copy is irrelevant).


    This function can be executed if the asyncio event loop is already running"""
    if buffer is None:
        return None
    ###
    copy = True # Apparently, sometimes the promise of not modifying the value is violated... for now, enforce a copy
    ###
    value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            newvalue = deepcopy(value)
            return newvalue
        else:
            return value

    value = _deserialize(buffer, checksum, celltype)
    if celltype not in text_types2:
        deserialize_cache[checksum, celltype] = value
        if copy:
            value = deepcopy(value)
    if not copy:
        id_value = id(value)
        serialize_cache[id_value, celltype] = buffer, value
    return value


from .serialize import serialize_cache
from ..cell import text_types2
from .evaluate import validate_text_celltype
from ..convert import validate_checksum
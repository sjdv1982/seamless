"""Functions to deserialize from buffer into value"""

import builtins
import logging
from copy import deepcopy
import json
import orjson
from silk.mixed.io import (  # pylint: disable=no-name-in-module
    deserialize as mixed_deserialize,
)
from silk.mixed import MAGIC_NUMPY
from seamless import Checksum

from seamless.util import lrucache2

logger = logging.getLogger(__name__)

deserialize_cache = lrucache2(10)


def _deserialize_plain(buffer):
    """"""
    """
    value, storage = mixed_deserialize(buffer)
    if storage != "pure-plain":
        raise TypeError
    """
    s = buffer.decode()
    s = s.rstrip("\n")
    try:
        value = orjson.loads(s)
    except json.JSONDecodeError:
        msg = s
        if len(msg) > 1000:
            msg = s[:920] + "..." + s[-50:]
        raise ValueError(msg) from None
    return value


def _deserialize(buffer: bytes, checksum: Checksum, celltype: str):
    from .evaluate import validate_text_celltype
    from .convert import validate_checksum

    if celltype == "silk":
        celltype = "mixed"
    if celltype not in celltypes:
        raise TypeError(celltype)
    checksum = Checksum(checksum)
    logger.debug(
        "DESERIALIZE: buffer of length {}, checksum {}".format(len(buffer), checksum)
    )
    if celltype in text_types2:
        s = buffer.decode()
        value = s.rstrip("\n")
        if checksum:
            validate_text_celltype(value, checksum, celltype)
    elif celltype == "plain":
        value = _deserialize_plain(buffer)
    elif celltype == "binary":
        if not buffer.startswith(MAGIC_NUMPY):
            raise TypeError
        value, _ = mixed_deserialize(buffer)  # fast enough for pure binary
    elif celltype == "mixed":
        value, _ = mixed_deserialize(buffer)
    elif celltype == "bytes":
        value = buffer
    elif celltype in ("str", "int", "float", "bool"):
        value = _deserialize_plain(buffer)
        if not isinstance(value, getattr(builtins, celltype)):
            value = getattr(builtins, celltype)(value)
    elif celltype == "checksum":
        try:
            value = buffer.decode()
            validate_checksum(value)
        except (ValueError, UnicodeDecodeError):
            value, storage = mixed_deserialize(buffer)
            if storage != "pure-plain":
                raise TypeError from None
            validate_checksum(value)
    else:
        raise NotImplementedError(celltype)

    return value


async def deserialize(buffer: str, checksum: Checksum, celltype: str, copy: bool):
    """Deserializes a buffer into a value
    The celltype must be one of the allowed celltypes.

    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed in a subprocess
     (and copy is irrelevant).
    CURRENTLY, copy IS IGNORED
    """
    if buffer is None:
        return None
    if celltype == "mixed":
        buffer_info: BufferInfo = buffer_cache.buffer_info.get(checksum)
        if buffer_info is not None:
            if buffer_info.is_json:
                celltype = "plain"
            elif buffer_info.is_numpy:
                celltype = "binary"
    value = deserialize_cache.get((checksum, celltype))
    ###
    copy = True
    # Apparently, sometimes the promise of not modifying the value
    # is violated... for now, enforce a copy
    ###
    if value is not None and not copy:
        return value

    """
    # ProcessPool is too slow, but ThreadPool works... do experiment with later
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        value = await loop.run_in_executor(
            executor, _deserialize, buffer, checksum, celltype
        )
    """
    value = _deserialize(buffer, checksum, celltype)

    if celltype not in text_types2 and not copy:
        deserialize_cache[checksum, celltype] = value

    if not copy:
        id_value = id(value)
        serialize_cache[id_value, celltype] = buffer, value
    return value


def deserialize_sync(buffer: str, checksum: Checksum, celltype: str, copy):
    """Deserializes a buffer into a value
    The celltype must be one of the allowed celltypes.

    First, it is attempted to retrieve the value from cache.
    In case of a cache hit, a copy is returned only if copy=True
    In case of a cache miss, deserialization is performed
    (and copy is irrelevant).
    CURRENTLY, copy IS IGNORED

    This function can be executed if the asyncio event loop is already running"""
    if buffer is None:
        return None
    checksum = Checksum(checksum)
    if celltype == "mixed":
        buffer_info: BufferInfo = buffer_cache.buffer_info.get(checksum)
        if buffer_info is not None:
            if buffer_info.is_json:
                celltype = "plain"
            elif buffer_info.is_numpy:
                celltype = "binary"
    ###
    copy = True
    # Apparently, sometimes the promise of not modifying the value
    # is violated... for now, enforce a copy
    ###
    value = None
    if checksum:
        value = deserialize_cache.get((checksum, celltype))
    if value is not None:
        if copy:
            newvalue = deepcopy(value)
            return newvalue
        else:
            return value

    value = _deserialize(buffer, checksum, celltype)
    if celltype not in text_types2 and not copy:
        deserialize_cache[checksum, celltype] = value
    if not copy:
        id_value = id(value)
        serialize_cache[id_value, celltype] = buffer, value
    return value


from .serialize import serialize_cache
from .cell import celltypes, text_types2
from .buffer_cache import buffer_cache, BufferInfo

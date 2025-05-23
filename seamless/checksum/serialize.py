"""Functions to serialize a value into a buffer"""

import logging

from seamless.util import lrucache2
from seamless.util import unchecksum
from seamless.checksum.celltypes import text_types

# serialize_cache: maps id(value),celltype to (buffer, value).
# Need to store (a ref to) value,
#  because id(value) is only unique while value does not die!!!
serialize_cache = lrucache2(10)

logger = logging.getLogger(__name__)


def _serialize(value, celltype: str):
    from seamless import Checksum
    from seamless.checksum.json import json_dumps

    if isinstance(value, Checksum):
        value = value.value
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
            buffer = (str(value).rstrip("\n") + "\n").encode()
    elif celltype == "plain":
        value = unchecksum(value)
        buffer = json_dumps(value, as_bytes=True) + b"\n"
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
        if celltype == "mixed":
            import numpy as np  # delayed import, since it takes ~1 sec in user time
            from silk.Silk import Silk
            from silk.mixed.io import (  # pylint: disable=no-name-in-module
                serialize as mixed_serialize,
            )

            if isinstance(value, Silk):
                value = value.unsilk
            else:
                value = unchecksum(value)
            buffer = mixed_serialize(value)
        elif celltype == "binary":
            if isinstance(value, bytes):
                buffer = value
            else:
                import numpy as np  # delayed import, since it takes ~1 sec in user time
                from silk.mixed.io import (  # pylint: disable=no-name-in-module
                    serialize as mixed_serialize,
                )

                value = np.array(value)
                buffer = mixed_serialize(value)
        else:
            raise TypeError(celltype)
    logger.debug("SERIALIZE: buffer of length {}".format(len(buffer)))
    return buffer


async def serialize(value, celltype: str, use_cache=True):
    """Serializes a value into a buffer
    The celltype must be one of the allowed celltypes.
    """

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


def serialize_sync(value, celltype: str, use_cache: bool = True):
    """Serializes a value into a buffer
    The celltype must be one of the allowed celltypes.
    This function can be executed if the asyncio event loop is already running"""
    if use_cache:
        id_value = id(value)
        buffer, _ = serialize_cache.get((id_value, celltype), (None, None))
        if buffer is not None:
            return buffer

    buffer = _serialize(value, celltype)  ### for now...
    if use_cache:
        serialize_cache[id_value, celltype] = buffer, value
    return buffer

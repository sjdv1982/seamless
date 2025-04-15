"""Get a buffer from its checksum"""

import asyncio
import seamless
from seamless import Checksum
from seamless.util.transformation import tf_get_buffer
from seamless.checksum.buffer_cache import buffer_cache

DEBUG = True
REMOTE_TIMEOUT = 5.0


def _get_buffer_from_transformation_cache(checksum):
    from seamless.workflow.core.cache.transformation_cache import transformation_cache

    transformation = transformation_cache.transformations.get(checksum)
    if transformation is not None:
        buffer = tf_get_buffer(transformation)
        if buffer is not None:
            buffer_cache.find_missing(checksum, buffer)
        return buffer


def get_buffer(
    checksum: Checksum, remote: bool, _done: set | None = None, deep: bool = False
):
    """Get a buffer from its checksum.
    What is tried:
    - buffer cache ("remote" and "deep" are passed to it)
    - transformation cache
    - Conversion using buffer_info

    Since it is synchronous, it doesn't try everything possible to obtain it.
    - Only the remote facilities from buffer cache are used
      (i.e. fairserver, direct download and read buffer server/folder),
    - No recomputation from transformation/expression is attempted
      (use fingertip for that).
    If seamless.workflow has been previously imported,
    the transformation cache is checked as well.

    If successful, add the buffer to local cache
    and/or write buffer server.
    Else, return None
    """
    from seamless.checksum.convert import try_convert_single

    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _done is not None and checksum in _done:
        return None
    buffer = buffer_cache.get_buffer(checksum, remote=remote, deep=deep)
    if buffer is not None:
        return buffer

    if seamless.SEAMLESS_WORKFLOW_IMPORTED:
        buffer = _get_buffer_from_transformation_cache(checksum)
        if buffer is not None:
            return buffer

    buffer_info = buffer_cache.get_buffer_info(
        checksum, sync_remote=remote, buffer_from_remote=False, force_length=False
    )
    if buffer_info is not None:
        d = buffer_info.as_dict()
        for k in d:
            if k.find("2") == -1:
                continue
            src, target = k.split("2")
            if _done is None:
                _done = set()
            _done.add(checksum)
            kcs = Checksum(d[k])
            target_buf = get_buffer(kcs, remote=remote, _done=_done)
            if target_buf is not None:
                try:
                    try_convert_single(
                        kcs,
                        target,
                        src,
                        buffer=target_buf,
                    )
                except Exception:
                    pass
                buffer = buffer_cache.get_buffer(checksum, remote=remote)
                if buffer is not None:
                    if buffer is not None:
                        buffer_cache.find_missing(checksum, buffer)
                    return buffer

    return None


GET_BUFFER_SEMAPHORE_SIZE = 100
_get_buffer_semaphore = None


async def get_buffer_async(
    checksum: Checksum, remote: bool, _done: set | None = None, deep: bool = False
):
    """Get a buffer from its checksum.
    What is tried:
    - buffer cache ("remote" and "deep" are passed to it)
    - transformation cache
    - Conversion using buffer_info

    Although asynchronous, it doesn't try everything possible to obtain it.
    - Only the remote facilities from buffer cache are used
      (i.e. fairserver, direct download and read buffer server/folder),
    - No recomputation from transformation/expression is attempted
      (use fingertip for that).
    If seamless.workflow has been previously imported,
    the transformation cache is checked as well.

    If successful, add the buffer to local cache
    and/or write buffer server.
    Else, return None
    """
    from seamless.checksum.convert import try_convert_single

    global _get_buffer_semaphore

    checksum = Checksum(checksum)
    if not checksum:
        return None
    if _done is not None and checksum in _done:
        return None

    if _get_buffer_semaphore is None:
        _get_buffer_semaphore = asyncio.Semaphore(GET_BUFFER_SEMAPHORE_SIZE)

    async with _get_buffer_semaphore:
        buffer = await buffer_cache.get_buffer_async(checksum, remote=remote, deep=deep)
    if buffer is not None:
        return buffer

    if seamless.SEAMLESS_WORKFLOW_IMPORTED:
        buffer = _get_buffer_from_transformation_cache(checksum)
        if buffer is not None:
            return buffer

    buffer_info = buffer_cache.get_buffer_info(
        checksum, sync_remote=remote, buffer_from_remote=False, force_length=False
    )
    if buffer_info is not None:
        d = buffer_info.as_dict()
        for k in d:
            if k.find("2") == -1:
                continue
            src, target = k.split("2")
            if _done is None:
                _done = set()
            _done.add(checksum)
            kcs = Checksum(d[k])
            target_buf = await get_buffer_async(kcs, remote=remote, _done=_done)
            if target_buf is not None:
                try:
                    try_convert_single(
                        kcs,
                        target,
                        src,
                        buffer=target_buf,
                    )
                except Exception:
                    pass
                buffer = await buffer_cache.get_buffer_async(checksum, remote=remote)
                if buffer is not None:
                    if buffer is not None:
                        buffer_cache.find_missing(checksum, buffer)
                    return buffer

    return None

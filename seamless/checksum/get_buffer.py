"""Get a buffer from its checksum"""

import seamless
from seamless import Checksum
from seamless.checksum.buffer_cache import buffer_cache

DEBUG = True
REMOTE_TIMEOUT = 5.0


def _get_buffer_from_transformation_cache(checksum):
    from seamless.workflow.core.cache.transformation_cache import (
        transformation_cache,
        tf_get_buffer,
    )

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
            target_buf = get_buffer(bytes.fromhex(d[k]), remote=remote, _done=_done)
            if target_buf is not None:
                try:
                    try_convert_single(
                        bytes.fromhex(d[k]),
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

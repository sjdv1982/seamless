import asyncio
import traceback
import os

DEBUG = True
REMOTE_TIMEOUT = 5.0

async def get_buffer_length_remote(checksum, remote_peer_id):
    clients = communion_client_manager.clients["buffer_length"]
    coros = []
    for client in clients:
        client_peer_id = client.get_peer_id()
        if client_peer_id != remote_peer_id:
            coro = client.submit(checksum)
            coros.append(coro)
    if not len(coros):
        return None
    futures = [asyncio.ensure_future(coro) for coro in coros]
    while 1:
        done, pending = await asyncio.wait(
            futures,
            timeout=REMOTE_TIMEOUT,
            return_when=asyncio.FIRST_COMPLETED
        )
        if len(done):
            for fut in done:
                if fut.exception() is not None:
                    if DEBUG:
                        try:
                            fut.result()
                        except:
                            traceback.print_exc()
                    continue
                length = fut.result()
                if length is None:
                    continue
                return length
        if not len(pending):
            break
    return None

async def get_buffer_remote(checksum, remote_peer_id):
    clients = communion_client_manager.clients["buffer"]
    coros = []
    for client in clients:
        client_peer_id = client.get_peer_id()
        if client_peer_id != remote_peer_id:
            coro = client.status(checksum)
            coros.append(coro)
    if not len(coros):
        return None
    futures = [asyncio.ensure_future(coro) for coro in coros]
    rev = {fut:n for n,fut in enumerate(futures)}
    best_client = None
    best_status = None
    while 1:
        done, pending = await asyncio.wait(
            futures,
            timeout=REMOTE_TIMEOUT,
            return_when=asyncio.FIRST_COMPLETED
        )
        if len(done):
            for fut in done:
                if fut.exception() is not None:
                    if DEBUG:
                        try:
                            fut.result()
                        except:
                            traceback.print_exc()
                    continue
                status = fut.result()
                if status == -1:
                    continue
                if best_status is None or status > best_status:
                    best_status = status
                    best_client = rev[fut]
                    if best_status == 1:
                        break
            if best_status == 1:
                break
        if not len(pending):
            break
    if best_client is not None:
        buffer = await clients[best_client].submit(checksum)
        if buffer is None:
            return None
        assert isinstance(buffer, bytes), buffer
        return buffer


def get_buffer(checksum, remote, _done=None, deep=False):
    """  Gets the buffer from its checksum.
What is tried:
- buffer cache ("remote" and "deep" are passed to it)
- transformation cache
- Conversion using buffer_info

Since it is synchronous, it doesn't try everything possible to obtain it.
- Only the remote facilities from buffer cache are used 
  (i.e. database, fairserver and buffer server), 
- Communion server is not used, as it is asynchronous.
- No recomputation from transformation/expression is attempted 
  (use fingertip for that).

If successful, add the buffer to local and/or database cache (with a tempref or a permanent ref).
Else, return None
"""
    from ...util import parse_checksum    
    from ..convert import try_convert_single
    checksum = parse_checksum(checksum, True)
    if checksum is None:
        return None
    if _done is not None and checksum in _done:
        return None
    buffer = buffer_cache.get_buffer(checksum, remote=remote, deep=deep)
    if buffer is not None:
        return buffer
    transformation = transformation_cache.transformations.get(checksum)
    if transformation is not None:
        buffer = tf_get_buffer(transformation)
        return buffer
    
    buffer_info = buffer_cache.get_buffer_info(checksum)
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
                        target, src,
                        buffer=target_buf,
                    )
                except Exception:
                    pass
                buffer = buffer_cache.get_buffer(checksum, remote=remote)
                if buffer is not None:
                    return buffer

    return None



from ..cache import CacheMissError
from ..cache.buffer_cache import buffer_cache
from ...communion_client import communion_client_manager
from ..cache.transformation_cache import transformation_cache, tf_get_buffer
import asyncio
import traceback

DEBUG = True
REMOTE_TIMEOUT = 5.0 

async def get_buffer_length_remote(checksum, buffer_cache, remote_peer_id):
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
    
async def get_buffer_remote(checksum, buffer_cache, remote_peer_id):
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
            raise CacheMissError(checksum.hex())
        assert isinstance(buffer, bytes), buffer
        if checksum in buffer_cache.missing_buffers:
            buffer_cache.missing_buffers.discard(checksum)
        buffer_cache.cache_buffer(checksum, buffer)
        return buffer


def get_buffer(checksum, buffer_cache):
    """  Gets the buffer from its checksum
- Check for a local checksum-to-buffer cache hit (synchronous)
- Else, check Redis cache (currently synchronous; make it async in a future version)
- Else, check transformation cache (if it hits, make buffer of it)
- Else, await remote checksum-to-buffer cache
- Else, the checksum will be fingertipped (if enabled)
- If successful, add the buffer to local and/or Redis cache (with a tempref or a permanent ref).
- If all fails, raise CacheMissError
"""     
    if checksum is None:
        return None
    buffer = checksum_cache.get(checksum)
    if buffer is not None:
        return buffer
    buffer = buffer_cache.get_buffer(checksum)
    if buffer is not None:
        return buffer
    transformation = transformation_cache.transformations.get(checksum)
    if transformation is not None:
        buffer = tf_get_buffer(transformation)
        return buffer
    raise CacheMissError(checksum.hex())



from .calculate_checksum import checksum_cache
from ..cache import CacheMissError
from ...communion_client import communion_client_manager
from ..cache.transformation_cache import transformation_cache, tf_get_buffer
import asyncio
from concurrent.futures import ProcessPoolExecutor

from ...pylru import lrucache
from ...get_hash import get_hash

calculate_checksum_cache = lrucache(100)
checksum_cache = lrucache(100)

async def calculate_checksum(buffer):
    if buffer is None:
        return None
    buf_id = id(buffer)
    cached_checksum = calculate_checksum_cache.get(buf_id)
    if cached_checksum:
        checksum_cache[cached_checksum] = buffer
        buffer_cache.cache_buffer(cached_checksum, buffer)
        return cached_checksum
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        checksum = await loop.run_in_executor(
            executor,
            get_hash,
            buffer
        )
    calculate_checksum_cache[buf_id] = checksum    
    checksum_cache[checksum] = buffer
    buffer_cache.cache_buffer(checksum, buffer)
    return checksum

def calculate_checksum_sync(buffer):
    if buffer is None:
        return None
    buf_id = id(buffer)
    cached_checksum = calculate_checksum_cache.get(buf_id)    
    if cached_checksum:
        checksum_cache[cached_checksum] = buffer
        buffer_cache.cache_buffer(cached_checksum, buffer)
        return cached_checksum
    checksum = get_hash(buffer)
    calculate_checksum_cache[buf_id] = checksum    
    checksum_cache[checksum] = buffer
    buffer_cache.cache_buffer(checksum, buffer)
    return checksum

from ..cache.buffer_cache import buffer_cache
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from ...pylru import lrucache
from ...get_hash import get_hash

# calculate_checksum_cache: maps id(buffer) to (checksum, buffer). 
# Need to store (a ref to) buffer, 
#  because id(buffer) is only unique while buffer does not die!!!
calculate_checksum_cache = lrucache(100)

checksum_cache = lrucache(100)

async def calculate_checksum(buffer):
    if buffer is None:
        return None
    buf_id = id(buffer)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))
    if cached_checksum is not None:
        checksum_cache[cached_checksum] = buffer
        buffer_cache.cache_buffer(cached_checksum, buffer)
        return cached_checksum
    if len(buffer) > 1000000:
        # ThreadPoolExecutor does not work...
        loop = asyncio.get_event_loop()    
        with ProcessPoolExecutor() as executor:
            checksum = await loop.run_in_executor(
                executor,
                get_hash,
                buffer
            )
    else:
        checksum = get_hash(buffer)
    calculate_checksum_cache[buf_id] = checksum, buffer   
    checksum_cache[checksum] = buffer
    buffer_cache.cache_buffer(checksum, buffer)
    return checksum

def calculate_checksum_sync(buffer):
    if buffer is None:
        return None
    buf_id = id(buffer)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))    
    if cached_checksum is not None:
        checksum_cache[cached_checksum] = buffer
        buffer_cache.cache_buffer(cached_checksum, buffer)
        return cached_checksum
    checksum = get_hash(buffer)
    calculate_checksum_cache[buf_id] = checksum, buffer 
    checksum_cache[checksum] = buffer
    buffer_cache.cache_buffer(checksum, buffer)
    return checksum

from ..cache.buffer_cache import buffer_cache


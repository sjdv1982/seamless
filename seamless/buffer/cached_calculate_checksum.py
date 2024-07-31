import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from seamless import Checksum
from seamless.util.pylru import lrucache
from seamless.buffer.calculate_checksum import calculate_checksum as calculate_checksum_func

# calculate_checksum_cache: maps id(buffer) to (checksum, buffer).
# Need to store (a ref to) buffer,
#  because id(buffer) is only unique while buffer does not die!!!

from seamless.util import lrucache2

calculate_checksum_cache = lrucache2(10)

checksum_cache = lrucache2(10)

async def cached_calculate_checksum(buffer):
    if buffer is None:
        return None
    assert isinstance(buffer, bytes)
    buf_id = id(buffer)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))
    cached_checksum = Checksum(cached_checksum)
    if cached_checksum:
        checksum_cache[cached_checksum] = buffer
        return Checksum(cached_checksum)
    if 0:
        # ThreadPoolExecutor does not work... ProcessPoolExecutor is slow. To experiment with later
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor() as executor:
            checksum = await loop.run_in_executor(
                executor,
                calculate_checksum_func,
                buffer
            )
    else:
        checksum = Checksum(calculate_checksum_func(buffer))
    calculate_checksum_cache[buf_id] = checksum, buffer
    checksum_cache[checksum] = buffer
    return checksum

def cached_calculate_checksum_sync(buffer):
    """This function can be executed if the asyncio event loop is already running"""
    if buffer is None:
        return None
    buf_id = id(buffer)
    assert isinstance(buffer, bytes)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))
    cached_checksum = Checksum(cached_checksum)
    if cached_checksum:
        checksum_cache[cached_checksum] = buffer
        return Checksum(cached_checksum)
    checksum = Checksum(calculate_checksum_func(buffer))
    calculate_checksum_cache[buf_id] = checksum, buffer
    checksum_cache[checksum] = buffer
    return checksum

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from ...pylru import lrucache
from ...calculate_checksum import calculate_checksum as calculate_checksum_func

class lrucache2(lrucache):
    """Version of lrucache that can be disabled"""
    _disabled = False
    def disable(self):
        self._disabled = True
    def enable(self):
        del self._disabled
    def __setitem__(self, key, value):
        if self._disabled:
            return
        super().__setitem__(key, value)


# calculate_checksum_cache: maps id(buffer) to (checksum, buffer).
# Need to store (a ref to) buffer,
#  because id(buffer) is only unique while buffer does not die!!!
calculate_checksum_cache = lrucache2(10)

checksum_cache = lrucache2(10)

async def calculate_checksum(buffer):
    if buffer is None:
        return None
    assert isinstance(buffer, bytes)
    buf_id = id(buffer)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))
    if cached_checksum is not None:
        checksum_cache[cached_checksum] = buffer
        return cached_checksum
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
        checksum = calculate_checksum_func(buffer)
    calculate_checksum_cache[buf_id] = checksum, buffer
    checksum_cache[checksum] = buffer
    return checksum

def calculate_checksum_sync(buffer):
    """This function can be executed if the asyncio event loop is already running"""
    if buffer is None:
        return None
    buf_id = id(buffer)
    assert isinstance(buffer, bytes)
    cached_checksum, _ = calculate_checksum_cache.get(buf_id, (None, None))
    if cached_checksum is not None:
        checksum_cache[cached_checksum] = buffer
        return cached_checksum
    checksum = calculate_checksum_func(buffer)
    calculate_checksum_cache[buf_id] = checksum, buffer
    checksum_cache[checksum] = buffer
    return checksum

from ...pylru import lrucache
from ...get_hash import get_hash

calculate_checksum_cache = lrucache(100)
checksum_cache = lrucache(100)

def calculate_checksum(buffer):
    buf_id = id(buffer)
    cached_checksum = calculate_checksum_cache.get(buf_id)
    if cached_checksum:
        return cached_checksum
    checksum = get_hash(buffer)
    cached_checksum[buf_id] = checksum
    checksum_cache[checksum] = buffer
    return checksum

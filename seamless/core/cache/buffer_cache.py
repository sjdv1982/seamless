# TODO: livegraph branch
# TODO: A single global value cache (see cachemanager)

import time
import weakref
from weakref import WeakValueDictionary
import functools
from collections import namedtuple

from .redis_client import redis_sinks, redis_caches

TEMP_KEEP_ALIVE = 20.0 # Keep buffer values alive for 20 secs after the last ref has expired

class BufferCache:
    """Checksum-to-buffer cache.
    Every buffer is referred to by a CacheManager (or more than one).

    Memory intensive. Like any other cache, does not persist unless offloaded.
    Cache items are directly serializable, and can be shared over the
    network, or offloaded to Redis.
     Keys are straightforward buffer checksums.
    """
    def __init__(self):
        self.buffer_cache = {} #checksum-to-buffer
        self.buffer_refcount = {} #buffer-checksum-to-refcount

    def cache_buffer(self, checksum, buffer):
        if checksum not in self.buffer_refcount:
            return
        if checksum in self.buffer_cache:
            return
        self.buffer_cache[checksum] = buffer
        redis_sinks.set_buffer(checksum, buffer)

    def incref(self, checksum):
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            return
        self.buffer_refcount[checksum] = 1
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            self.cache_buffer(checksum, buffer)

    def decref(self, checksum, from_temp=False):
        if not from_temp and self.buffer_refcount[checksum] == 1:
            tempref = functools.partial(self.decref, checksum, from_temp=True)
            temprefmanager.add_ref(tempref, TEMP_KEEP_ALIVE)
            return
        self.buffer_refcount[checksum] -= 1
        if self.buffer_refcount[checksum] == 0:
            self.buffer_cache.pop(checksum)
            self.buffer_refcount.pop(checksum)

    def get_buffer(self, checksum):
        if checksum is None:
            return None
        buffer = self.buffer_cache.get(checksum)
        if buffer is not None:
            return buffer
        return redis_caches.get_buffer(checksum)

    def buffer_check(self, checksum):
        """For the communionserver..."""
        assert checksum is not None
        if checksum in self.buffer_cache:
            return True        
        return redis_caches.has_buffer(checksum)

buffer_cache = BufferCache()

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
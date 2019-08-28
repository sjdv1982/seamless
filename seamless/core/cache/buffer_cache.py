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
        # Buffer length caches (never expire)
        self.small_buffers = set()
        self.buffer_length = {} #checksum-to-bufferlength (large buffers)

    def cache_buffer(self, checksum, buffer):
        if checksum not in self.buffer_refcount:
            self.buffer_refcount[checksum] = 1
            tempref = functools.partial(self.decref, checksum, from_temp=True)
            temprefmanager.add_ref(tempref, TEMP_KEEP_ALIVE)            
        if checksum in self.buffer_cache:
            return            
        self.buffer_cache[checksum] = buffer
        redis_sinks.set_buffer(checksum, buffer)
        l = len(buffer)
        if l < 1000:
            if checksum not in self.small_buffers:
                self.small_buffers.add(checksum)
                redis_sinks.add_small_buffer(checksum)
        else:
            if checksum not in self.buffer_length:
                self.buffer_length[checksum] = l
                redis_sinks.set_buffer_length(checksum, l)

    def incref(self, checksum):
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            return
        self.buffer_refcount[checksum] = 1
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            self.cache_buffer(checksum, buffer)
        else:
            assert self.get_buffer(checksum) is not None

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

    def get_buffer_length(self, checksum):
        if checksum is None:
            return None
        if checksum in self.small_buffers:
            return 1
        length = self.buffer_length.get(checksum)
        if length is not None:
            return length
        return redis_caches.get_buffer_length(checksum)

    def buffer_check(self, checksum):
        """For the communion_server..."""
        assert checksum is not None
        if checksum in self.buffer_cache:
            return True        
        return redis_caches.has_buffer(checksum)

buffer_cache = BufferCache()

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
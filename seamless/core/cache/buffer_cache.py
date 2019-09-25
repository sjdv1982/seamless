# TODO: livegraph branch
# TODO: A single global value cache (see cachemanager)

import time
import weakref
import traceback
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
        self.missing_buffers = set()

    def cache_buffer(self, checksum, buffer):
        assert checksum is not None
        assert isinstance(buffer, bytes)
        if checksum not in self.buffer_refcount:
            self.buffer_refcount[checksum] = 1
            tempref = functools.partial(self.decref, checksum, from_temp=True)
            temprefmanager.add_ref(tempref, TEMP_KEEP_ALIVE)            
        if checksum in self.buffer_cache:
            return            
        self.buffer_cache[checksum] = buffer
        self.missing_buffers.discard(checksum)
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
        #print("INCREF", checksum.hex())
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            if checksum not in self.missing_buffers:
                return
        else:
            self.buffer_refcount[checksum] = 1
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            self.cache_buffer(checksum, buffer)
        else:
            if self.get_buffer(checksum) is None:
                self.missing_buffers.add(checksum)

    def decref(self, checksum, from_temp=False):
        """
        if not from_temp:
            print("DECREF", checksum.hex())
        """
        if checksum not in self.buffer_refcount:
            print("WARNING: double decref, %s" % checksum.hex())            
            return
        if not from_temp and self.buffer_refcount[checksum] == 1:
            tempref = functools.partial(self.decref, checksum, from_temp=True)
            temprefmanager.add_ref(tempref, TEMP_KEEP_ALIVE)
            return
        self.buffer_refcount[checksum] -= 1
        if self.buffer_refcount[checksum] == 0:            
            if checksum in self.missing_buffers:
                self.missing_buffers.pop(checksum)
            else:
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
from . import CacheMissError
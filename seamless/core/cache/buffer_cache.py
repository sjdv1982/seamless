import time
import weakref
import traceback
from weakref import WeakValueDictionary
import functools
from collections import namedtuple

from .database_client import database_sink, database_cache


TEMP_KEEP_ALIVE = 20.0 # Keep buffer values alive for 20 secs after the last ref has expired
TEMP_KEEP_ALIVE_SMALL = 3600.0 # Keep small buffer values (< 10 000 bytes) alive for an hour

class BufferCache:
    """Checksum-to-buffer cache.
    Every buffer is referred to by a CacheManager (or more than one).

    Memory intensive. Like any other cache, does not persist unless offloaded.
    Cache items are directly serializable, and can be shared over the
    network, or offloaded to a database.
    Keys are straightforward buffer checksums.

    NOTE: if there is a database sink, buffers are not maintained in local cache.
    Refcounts are still maintained.
    """
    def __init__(self):
        self.buffer_cache = {} #local cache, checksum-to-buffer
        self.buffer_refcount = {} #buffer-checksum-to-refcount
        # Buffer length cache (never expire)
        self.buffer_length = {} #checksum-to-bufferlength

        self.missing_buffers = set()

    def cache_buffer(self, checksum, buffer, authoritative):
        assert checksum is not None
        assert isinstance(buffer, bytes)
        l = len(buffer)
        if checksum not in self.buffer_length:
            self.buffer_length[checksum] = l
        database_sink.set_buffer_length(checksum, l)
        if checksum not in self.buffer_refcount:
            self.incref_temp(checksum)
        no_local = False
        if database_sink.active:
            if not database_sink.has_buffer(checksum):
                database_sink.set_buffer(checksum, buffer, authoritative)
            if database_cache.active:
                no_local = True
        if not no_local:
            if checksum in self.buffer_cache:
                return
            self.buffer_cache[checksum] = buffer
            self.missing_buffers.discard(checksum)

    def incref_temp(self, checksum):
        print("INCREF TEMP", checksum.hex())
        if checksum not in self.buffer_refcount:
            self.buffer_refcount[checksum] = 0
        self.buffer_refcount[checksum] += 1
        tempref = functools.partial(self.decref, checksum, from_temp=True)
        keep_alive = TEMP_KEEP_ALIVE_SMALL\
            if self.buffer_length.get(checksum, 10000) < 10000 \
            else TEMP_KEEP_ALIVE
        temprefmanager.add_ref(tempref, keep_alive)


    def incref(self, checksum, authoritative):
        print("INCREF     ", checksum.hex())
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            if checksum not in self.missing_buffers:
                return
        else:
            self.buffer_refcount[checksum] = 1
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            self.cache_buffer(checksum, buffer, authoritative)
        else:
            if self.get_buffer(checksum) is None:
                self.missing_buffers.add(checksum)

    def decref(self, checksum, from_temp=False):
        if not from_temp:
            print("DECREF     ", checksum.hex())
        else:
            print("DECREF TEMP", checksum.hex())
        if checksum not in self.buffer_refcount:
            print("WARNING: double decref, %s" % checksum.hex())
            return
        if not from_temp and self.buffer_refcount[checksum] == 1:
            self.buffer_refcount[checksum] -= 1
            self.incref_temp(checksum)
            return
        self.buffer_refcount[checksum] -= 1
        if self.buffer_refcount[checksum] == 0:
            if checksum in self.missing_buffers:
                self.missing_buffers.remove(checksum)
            else:
                self.buffer_cache.pop(checksum, None)
            self.buffer_refcount.pop(checksum)

    def get_buffer(self, checksum):
        if checksum is None:
            return None
        buffer = self.buffer_cache.get(checksum)
        if buffer is not None:
            return buffer
        return database_cache.get_buffer(checksum)

    def get_buffer_length(self, checksum):
        if checksum is None:
            return None
        length = self.buffer_length.get(checksum)
        if length is not None:
            return length
        length = database_cache.get_buffer_length(checksum)
        if length is not None:
            return length
        buf = self.get_buffer(checksum)
        if buf is not None:
            return len(buf)

    def buffer_check(self, checksum):
        """For the communion_server..."""
        assert checksum is not None
        if checksum in self.buffer_cache:
            return True
        return database_cache.has_buffer(checksum)

buffer_cache = BufferCache()
buffer_cache.database_cache = database_cache
buffer_cache.database_sink = database_sink

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
from . import CacheMissError
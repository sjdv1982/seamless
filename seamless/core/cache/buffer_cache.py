import time
import weakref
import traceback
from weakref import WeakValueDictionary
import functools
from collections import namedtuple

from .database_client import database_sink, database_cache

# Note: non-authoritative buffers are not cached locally, but they are sent into the database sink
LIFETIME_TEMP = 20.0 # buffer_cache keeps buffer values alive for 20 secs
LIFETIME_TEMP_SMALL = 3600.0 # buffer_cache keeps small buffer values (< 10 000 bytes) alive for an hour
LIFETIME_TF_RESULT = 20.0 # buffer_transformation_result keeps remote/dummy transformation results alive for 20 secs
LIFETIME_TF_RESULT_SMALL = 3600.0 # buffer_transformation_result keeps small (< 10 000 bytes) remote/dummy transformation results alive for an hour

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

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
        self.last_time = {}
        self.buffer_refcount = {} #buffer-checksum-to-refcount
        # Buffer length cache (never expire)
        self.buffer_length = {} #checksum-to-bufferlength
        self.non_authoritative = set()
        self.missing = set()

    def _check_delete_buffer(self, checksum):
        if checksum not in self.last_time:
            return
        t = time.time()
        l = self.buffer_length.get(checksum, 999999999)
        lifetime = LIFETIME_TEMP_SMALL if l < 10000 else LIFETIME_TEMP
        last_time = self.last_time[checksum]
        curr_lifetime = t - last_time
        if curr_lifetime < lifetime:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = max(lifetime-curr_lifetime, 1)
            temprefmanager.add_ref(func, delay, on_shutdown=False)
            return

        self.last_time.pop(checksum)
        if checksum in self.buffer_refcount:
            local = (not database_sink.active) or (not database_cache.active)
            if local and checksum not in self.non_authoritative:
                return
        self.buffer_cache.pop(checksum, None)

    def _update_time(self, checksum, buffer_length=None):
        t = time.time()
        if buffer_length is None:
            buffer_length = 9999999
        if checksum not in self.last_time:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = LIFETIME_TEMP_SMALL if buffer_length < 10000 else LIFETIME_TEMP
            temprefmanager.add_ref(func, delay, on_shutdown=False)
        self.last_time[checksum] = t

    def cache_buffer(self, checksum, buffer):
        """Caches a buffer locally for a short time, without incrementing its refcount
        Does not write into the database.
        If the buffer already has a refcount AND a database is active, nothing happens
        """
        assert checksum is not None
        assert isinstance(buffer, bytes)
        #print("LOCAL CACHE", checksum.hex())
        local = (not database_sink.active) or (not database_cache.active)
        if not local and checksum in self.buffer_refcount:
            return
        self._update_time(checksum, len(buffer))
        if checksum not in self.buffer_cache:
            self.buffer_cache[checksum] = buffer

        if checksum in self.missing:
            self.missing.discard(checksum)
            if database_sink.active:
                database_sink.set_buffer(checksum, buffer, authoritative)

    def incref_buffer(self, checksum, buffer, authoritative):
        """Caches a buffer and increments its refcount.
        If it is the first reference, it is written into the database;
          if there is no database, it is written into local cache instead
        If it is not the first reference but the first authoritative one,
         the buffer is re-written into the database"""
        assert checksum is not None
        assert isinstance(buffer, bytes)
        l = len(buffer)
        if checksum not in self.buffer_length:
            self.buffer_length[checksum] = l
            database_sink.set_buffer_length(checksum, l)
        self._incref(checksum, authoritative, buffer)

    def _incref(self, checksum, authoritative, buffer):
        #print("INCREF     ", checksum.hex(), authoritative, buffer is None)
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            if database_sink.active:
                if authoritative and checksum in self.non_authoritative:
                    self.non_authoritative.discard(checksum)
                    if buffer is None:
                        buffer = self.get_buffer(checksum)
                    if buffer is not None:
                        # TODO: this will normally not work. Add a database_sink "make_authoritative" API function!
                        database_sink.set_buffer(checksum, buffer, authoritative)
            if buffer is not None and checksum in self.missing:
                self.missing.discard(checksum)
                local = (not database_sink.active) or (not database_cache.active)
                if authoritative and local:
                    if checksum not in self.buffer_cache:
                        self.buffer_cache[checksum] = buffer
        else:
            self.buffer_refcount[checksum] = 1
            local = (not database_sink.active) or (not database_cache.active)
            if not authoritative:
                self.non_authoritative.add(checksum)
            if buffer is None:
                buffer = self.buffer_cache.get(checksum)
            if buffer is not None:
                if database_sink.active:
                    database_sink.set_buffer(checksum, buffer, authoritative)
                if local:
                    if authoritative:
                        if checksum not in self.buffer_cache:
                            self.buffer_cache[checksum] = buffer
                    else:
                        self.cache_buffer(checksum, buffer)
            else:
                print("MISS", checksum.hex(), checksum in self.buffer_cache)
                raise Exception ###
                self.missing.add(checksum)
            if not local and checksum in self.last_time:
                self.last_time.pop(checksum)
                self.buffer_cache.pop(checksum)

    def incref(self, checksum, authoritative):
        """Increments the refcount of a buffer checksum.

        If it is the first authoritative reference, it is re-written into the database
        (if the buffer can be retrieved)"""

        buffer = None
        if checksum not in self.buffer_refcount:
            buffer = self.buffer_cache.get(checksum)
        return self._incref(checksum, authoritative, buffer)

    def decref(self, checksum):
        """Decrements the refcount of a buffer checksum, cached with incref_buffer
        If the refcount reaches zero, and there is no database,
         it will be added to local cache using cache_buffer.
        This means that it will remain accessible for a short while
        """
        #print("DECREF     ", checksum.hex())
        if checksum not in self.buffer_refcount:
            print_warning("double decref, %s" % checksum.hex())
            return
        self.buffer_refcount[checksum] -= 1
        if self.buffer_refcount[checksum] == 0:
            self.buffer_refcount.pop(checksum)
            self.missing.discard(checksum)
            local = (not database_sink.active) or (not database_cache.active)
            #print("DESTROY", checksum.hex(), local, checksum in self.buffer_cache)
            if local:
                buffer = self.get_buffer(checksum)
                if buffer is not None:  # should be ok normally
                    self.cache_buffer(checksum, buffer)

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

    def destroy(self):
        if self.buffer_cache is None:
            return
        if len(self.buffer_refcount):
            print_warning("buffer cache, %s buffers undestroyed" % len(self.buffer_refcount))
        self.buffer_cache = None
        self.last_time = None
        self.buffer_refcount = None
        self.buffer_length = None
        self.non_authoritative = None


buffer_cache = BufferCache()
buffer_cache.database_cache = database_cache
buffer_cache.database_sink = database_sink

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
from . import CacheMissError
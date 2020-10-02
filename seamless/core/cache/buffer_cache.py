import time
import weakref
import traceback
from weakref import WeakValueDictionary
import functools
from collections import namedtuple

from .database_client import database_sink, database_cache

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
    Buffers can be shared over the network, or offloaded to a database.
    Keys are straightforward buffer checksums.

    NOTE: if there is a database active, buffers are normally not maintained in local cache.
    Refcounts are still maintained; a buffer with a refcount is sure to have been written into the database

    It is always possible to cache a buffer that has no refcount into local cache for a short while
    """


    LIFETIME_TEMP = 20.0 # buffer_cache keeps unreferenced/non-persistent buffer values alive for 20 secs
    LIFETIME_TEMP_SMALL = 3600.0 # buffer_cache keeps unreferenced/non-persistent small buffer values (< 10 000 bytes) alive for an hour
    LOCAL_MODE_FULL_PERSISTENCE = True # If true, all non-authoritative buffers are persistent in local mode, i.e. when there is no database.
                                       # Else, only authoritative buffers are persistent.
                                       # Unreferenced buffers are never persistent.

    def __init__(self):
        self.buffer_cache = {} #local cache, checksum-to-buffer
        self.last_time = {}
        self.buffer_refcount = {} #buffer-checksum-to-refcount
        # Buffer length cache (never expire)
        self.buffer_length = {} #checksum-to-bufferlength
        self.non_persistent = set()
        self.missing = set()

    def _is_persistent(self, authoritative):
        if authoritative:
            persistent = True
        else:
            local = (not database_sink.active) or (not database_cache.active)
            if not local:
                persistent = False
            else:
                persistent = self.LOCAL_MODE_FULL_PERSISTENCE
        return persistent

    def _check_delete_buffer(self, checksum):
        if checksum not in self.last_time:
            return
        t = time.time()
        l = self.buffer_length.get(checksum, 999999999)
        lifetime = self.LIFETIME_TEMP_SMALL if l < 10000 else self.LIFETIME_TEMP
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
            if local and checksum not in self.non_persistent:
                return
        self.buffer_cache.pop(checksum, None)

    def _update_time(self, checksum, buffer_length=None):
        t = time.time()
        if buffer_length is None:
            buffer_length = 9999999
        if checksum not in self.last_time:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = self.LIFETIME_TEMP_SMALL if buffer_length < 10000 else self.LIFETIME_TEMP
            temprefmanager.add_ref(func, delay, on_shutdown=False)
        self.last_time[checksum] = t

    def cache_buffer(self, checksum, buffer):
        """Caches a buffer locally for a short time, without incrementing its refcount
        Does not write into the database.
        The checksum can be incref'ed later, without the need to re-provide the buffer.

        If the buffer already has a refcount:
            - If the buffer was previously missing
        If the buffer already has a refcount AND a database is active, nothing at all happens
        """
        if checksum is None:
            return
        assert isinstance(buffer, bytes)
        #print("LOCAL CACHE", checksum.hex())
        self._update_time(checksum, len(buffer))
        local = (not database_sink.active) or (not database_cache.active)
        if local or checksum not in self.buffer_refcount:
            if checksum not in self.buffer_cache:
                self.buffer_cache[checksum] = buffer
        if checksum in self.missing:
            print_debug("Found missing buffer (1): {}".format(checksum.hex()))
            self.missing.discard(checksum)
            if database_sink.active:
                persistent = checksum not in self.non_persistent
                database_sink.set_buffer(checksum, buffer, persistent)

    def incref_buffer(self, checksum, buffer, authoritative):
        """Increments the refcount of a known buffer.
        See the documentation of self.incref.
        """
        assert checksum is not None
        assert isinstance(buffer, bytes)
        l = len(buffer)
        if checksum not in self.buffer_length:
            self.buffer_length[checksum] = l
            database_sink.set_buffer_length(checksum, l)
        self._incref(checksum, self._is_persistent(authoritative), buffer)

    def _incref(self, checksum, persistent, buffer):
        #print("INCREF     ", checksum.hex(), persistent, buffer is None)
        if checksum in self.buffer_refcount:
            self.buffer_refcount[checksum] += 1
            if database_sink.active:
                if persistent and checksum in self.non_persistent:
                    self.non_persistent.discard(checksum)
                    if database_cache.active and buffer is None:
                        buffer = self.get_buffer(checksum)
                    if buffer is not None:
                        # TODO: this will normally not work. Add a database_sink "make_persistent" API function!
                        database_sink.set_buffer(checksum, buffer, persistent)
            if buffer is not None and checksum in self.missing:
                assert isinstance(buffer, bytes)
                print_debug("Found missing buffer (2): {}".format(checksum.hex()))
                self.missing.discard(checksum)
                local = (not database_sink.active) or (not database_cache.active)
                if persistent and local:
                    if checksum not in self.buffer_cache:
                        self.buffer_cache[checksum] = buffer
                if not local:
                    if not database_sink.has_buffer(checksum):
                        database_sink.set_buffer(checksum, buffer, persistent)
        else:
            self.buffer_refcount[checksum] = 1
            local = (not database_sink.active) or (not database_cache.active)
            if not persistent:
                self.non_persistent.add(checksum)
            if buffer is None:
                buffer = self.buffer_cache.get(checksum)
            if buffer is not None:
                if database_sink.active:
                    if not database_sink.has_buffer(checksum):
                        database_sink.set_buffer(checksum, buffer, persistent)
                if local:
                    if persistent:
                        if checksum not in self.buffer_cache:
                            self.buffer_cache[checksum] = buffer
                    else:
                        self.cache_buffer(checksum, buffer)
            else:
                if database_cache.active and database_cache.has_buffer(checksum):
                    pass
                else:
                    print_debug("Incref checksum of missing buffer: {}".format(checksum.hex()))
                    self.missing.add(checksum)
            if not local and checksum in self.last_time:
                self.last_time.pop(checksum)
                self.buffer_cache.pop(checksum, None)

    def incref(self, checksum, authoritative):
        """Increments the refcount of a buffer checksum.

        If the buffer cannot be retrieved, it is registered as missing.
        Otherwise:
        - If it is the first *non-persistent* reference, and a database is active,
           it is moved from local cache into the database. If there is no database,
           it will remain in local cache for a short while.
        - If it is the first *persistent* reference,
           it is written persistently into the database. If there is no database,
           it will now remain in local cache as long as there are refs to it.

        If a database is active, only authoritative buffers are considered persistent
        If there is no database, all buffers are considered persistent,
         unless LOCAL_MODE_FULL_PERSISTENCE is disabled, in which case only authoritative buffers are.
        """

        buffer = None
        if checksum not in self.buffer_refcount:
            buffer = self.buffer_cache.get(checksum)
        return self._incref(checksum, self._is_persistent(authoritative), buffer)

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
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
            return buffer
        buffer = self.buffer_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
            return buffer
        buffer = database_cache.get_buffer(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
        return buffer

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
        self.non_persistent = None


buffer_cache = BufferCache()
buffer_cache.database_cache = database_cache
buffer_cache.database_sink = database_sink

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
from . import CacheMissError
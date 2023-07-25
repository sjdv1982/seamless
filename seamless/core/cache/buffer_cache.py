import time
import functools

from silk.mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED

from seamless.core.buffer_info import BufferInfo

from . import buffer_remote

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

empty_dict_checksum = 'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c'
empty_list_checksum = '7b41ad4a50b29158e075c6463133761266adb475130b8e886f2f5649070031cf'

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


    SMALL_BUFFER_LIMIT = 100000
    LIFETIME_TEMP = 20.0 # buffer_cache keeps unreferenced buffer values alive for 20 secs
    LIFETIME_TEMP_SMALL = 600.0 # buffer_cache keeps unreferenced small buffer values (< SMALL_BUFFER_LIMIT bytes) alive for 10 minutes

    def __init__(self):
        self.buffer_cache = {} #local cache, checksum-to-buffer
        self.last_time = {}
        self.buffer_refcount = {} #buffer-checksum-to-refcount
        # Buffer info cache (never expire)
        self.buffer_info = {} #checksum-to-buffer-info
        self.synced_buffer_info = set()  #set of bufferinfo checksums that are in-sync with the database
        self.missing = set()

        self.incref_buffer(bytes.fromhex(empty_dict_checksum), b'{}\n', True)
        self.incref_buffer(bytes.fromhex(empty_list_checksum), b'[]\n', True)

    def _check_delete_buffer(self, checksum):
        if checksum not in self.last_time:
            return
        t = time.time()
        l = self.buffer_info.get(checksum, {}).get("length", 999999999)
        lifetime = self.LIFETIME_TEMP_SMALL if l < self.SMALL_BUFFER_LIMIT else self.LIFETIME_TEMP
        last_time = self.last_time[checksum]
        curr_lifetime = t - last_time
        if curr_lifetime < lifetime:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = max(lifetime-curr_lifetime, 1)
            temprefmanager.add_ref(func, delay, on_shutdown=False)
            return
        self._uncache_buffer(checksum)

    def _uncache_buffer(self, checksum):
        self.last_time.pop(checksum, None)
        if checksum in self.buffer_refcount:
            if not buffer_remote.can_delete_buffer(checksum):
                return
        self.buffer_cache.pop(checksum, None)


    def _update_time(self, checksum, buffer_length=None):
        t = time.time()
        if buffer_length is None:
            buffer_length = 9999999
        if checksum not in self.last_time:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = self.LIFETIME_TEMP_SMALL if buffer_length < self.SMALL_BUFFER_LIMIT else self.LIFETIME_TEMP
            temprefmanager.add_ref(func, delay, on_shutdown=False)
        self.last_time[checksum] = t

    def cache_buffer(self, checksum, buffer):
        """Caches a buffer locally for a short time, without incrementing its refcount
        Does not write into the database.
        The checksum can be incref'ed later, without the need to re-provide the buffer.
        """
        if checksum is None:
            return
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        assert isinstance(buffer, bytes)
        #print("LOCAL CACHE", checksum.hex())
        if checksum not in self.buffer_refcount:
            self._update_time(checksum, len(buffer))
        self.update_buffer_info(checksum, "length", len(buffer), sync_remote=False)
        if not buffer_remote.is_known(checksum):
            self.buffer_cache[checksum] = buffer
        if checksum in self.missing:
            print_debug("Found missing buffer (1): {}".format(checksum.hex()))
            self.missing.discard(checksum)
            buffer_remote.write_buffer(checksum, buffer)

    def incref_buffer(self, checksum, buffer, authoritative):
        """Increments the refcount of a known buffer.
        See the documentation of self.incref.
        """
        assert checksum is not None
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        assert isinstance(buffer, bytes)
        l = len(buffer)
        self.update_buffer_info(checksum, "length", l, sync_remote=False)
        return self._incref([checksum], authoritative, [buffer])

    def _incref(self, checksums, authoritative, buffers):
        for n, checksum in enumerate(checksums):
            if checksum.hex() in (empty_dict_checksum, empty_list_checksum):
                continue
            buffer = None
            if buffers is not None:
                buffer = buffers[n]
            #print("INCREF     ", checksum.hex(), buffer is None)
            if checksum in self.buffer_refcount:
                self.buffer_refcount[checksum] += 1
                if buffer is not None and checksum in self.missing:
                    assert isinstance(buffer, bytes)
                    print_debug("Found missing buffer (2): {}".format(checksum.hex()))
                    self.missing.discard(checksum)
                    if not buffer_remote.is_known(checksum):
                        self.buffer_cache[checksum] = buffer
                    buffer_remote.write_buffer(checksum, buffer)
            else:
                self.buffer_refcount[checksum] = 1
                if buffer is None:
                    buffer = self.buffer_cache.get(checksum)
                caching = False
                if buffer is not None:
                    if not buffer_remote.is_known(checksum):
                        self.buffer_cache[checksum] = buffer
                        caching = True
                    buffer_remote.write_buffer(checksum, buffer)
                else:
                    if not buffer_remote.is_known(checksum):
                        if n < 10:
                            print_debug("Incref checksum of missing buffer: {}".format(checksum.hex()))
                        elif n == 10:
                            print_debug("... ({} more buffers)".format(len(checksums) - 10))
                        self.missing.add(checksum)
                if checksum in self.last_time:
                    self.last_time.pop(checksum)
                    if not caching:
                        self.buffer_cache.pop(checksum, None)

    def incref(self, checksum, authoritative):
        """Increments the refcount of a buffer checksum.

        If the buffer cannot be retrieved, it is registered as missing.
        Otherwise, it is moved from local cache into the database. 
        If there is no database, it will remain in local cache for a short while.
        """
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        buffer = None
        if checksum not in self.buffer_refcount:
            buffer = self.buffer_cache.get(checksum)
        self._incref([checksum], authoritative, [buffer])

    def _decref(self, checksums):
        for checksum in checksums:
            if checksum.hex() in (empty_dict_checksum, empty_list_checksum):
                continue
            if checksum not in self.buffer_refcount:
                print_warning("double decref, %s" % checksum.hex())
                return
            self.buffer_refcount[checksum] -= 1
            if self.buffer_refcount[checksum] == 0:
                self.buffer_refcount.pop(checksum)
                self.missing.discard(checksum)
                can_delete = buffer_remote.can_delete_buffer(checksum)
                #print("DESTROY", checksum.hex(), can_delete, checksum in self.buffer_cache)
                if can_delete and checksum in self.buffer_cache:
                    buffer = self.get_buffer(checksum)
                    if buffer is not None:  # should be ok normally
                        self.cache_buffer(checksum, buffer)

    def decref(self, checksum):
        """Decrements the refcount of a buffer checksum, cached with incref_buffer
        If the refcount reaches zero, and there is no database,
         it will be added to local cache using cache_buffer.
        This means that it will remain accessible for a short while
        """
        #print("DECREF     ", checksum.hex())
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        return self._decref([checksum])

    def get_buffer(self, checksum, *, remote=True, deep=False):
        from ... import fair     
        if checksum is None:
            return None
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        if checksum.hex() == empty_dict_checksum:
            return b'{}\n'
        elif checksum.hex() == empty_list_checksum:
            return b'[]\n'
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
            return buffer
        buffer = self.buffer_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes), type(buffer)
            return buffer
        if remote:
            try:
                buffer = buffer_remote.get_buffer(checksum)
            except Exception:
                import traceback
                traceback.print_exc()
            if buffer is not None:
                assert isinstance(buffer, bytes)
            else:
                buffer = fair.get_buffer(checksum, deep=deep)
                if buffer is not None:
                    assert isinstance(buffer, bytes)
                    buffer_cache.cache_buffer(checksum, buffer)
                    return buffer

        return buffer

    def _sync_buffer_info_from_remote(self, checksum): 
        local_buffer_info = self.buffer_info[checksum]       
        if checksum in self.synced_buffer_info:
            return
        buffer_info_remote = database.get_buffer_info(checksum)
        if buffer_info_remote is None:
            return
        buffer_info_remote_old = buffer_info_remote.as_dict()
        buffer_info_remote.update(local_buffer_info)
        local_buffer_info.update(buffer_info_remote)
        if buffer_info_remote.as_dict() == buffer_info_remote_old:
            self.synced_buffer_info.add(checksum)

    def _sync_buffer_info_to_remote(self, checksum):
        local_buffer_info = self.buffer_info[checksum]        
        if checksum in self.synced_buffer_info:
            return
        database.set_buffer_info(checksum, local_buffer_info)
        self.synced_buffer_info.add(checksum)

    def get_buffer_info(self, checksum, *, sync_remote, buffer_from_remote, force_length):
        if checksum is None:
            return None
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        buffer_info = self.buffer_info.get(checksum)
        if buffer_info is None:
            buffer_info = BufferInfo(checksum)
            self.buffer_info[checksum] = buffer_info
        if sync_remote:
            self._sync_buffer_info_from_remote(checksum)
        if not force_length or buffer_info.length is not None:
            return buffer_info

        if buffer_from_remote:
            remotes = [False, True]
        else:
            remotes = [False]

        for do_remote in remotes:
            buf = self.get_buffer(checksum, remote=do_remote)
            if buf is not None:
                length = len(buf)
                self.update_buffer_info(
                    checksum, "length", length,
                    sync_remote=sync_remote,
                    no_sync_from_remote=True,
                )
                break
        else:
            raise CacheMissError(checksum.hex())
        
        return buffer_info


    def update_buffer_info(self, checksum, attr, value, *, sync_remote, no_sync_from_remote=False):
        co_flags = {
            "is_json": ("is_utf8",),
            "json_type": ("is_json",),
            "is_json_numeric_array": ("is_json",),
            "is_json_numeric_scalar": ("is_json",),
            "dtype": ("is_numpy",),
            "shape": ("is_numpy",),
        }
        anti_flags = {
            "is_json": ("is_numpy", "is_seamless_mixed"),
            "is_numpy": ("is_json", "is_seamless_mixed"),
            "is_seamless_mixed": ("is_json", "is_numpy"),
        }

        buffer_info = self.buffer_info.get(checksum)
        if buffer_info is None:
            buffer_info = BufferInfo(checksum)
            self.buffer_info[checksum] = buffer_info
        if sync_remote and (not no_sync_from_remote) and checksum not in self.synced_buffer_info:
            self._sync_buffer_info_from_remote(checksum)
        if buffer_info[attr] != value:
            self.synced_buffer_info.discard(checksum)
        buffer_info[attr] = value
        if value:
            for f in co_flags.get(attr, []):
                self.update_buffer_info(checksum, f, True, sync_remote=False)
            for f in anti_flags.get(attr, []):
                self.update_buffer_info(checksum, f, False, sync_remote=False)
        elif value == False:
            for f in co_flags.get(attr, []):
                self.update_buffer_info(checksum, f, False, sync_remote=False)
        if sync_remote:
            self._sync_buffer_info_to_remote(checksum)

    def guarantee_buffer_info(self, checksum:bytes, celltype:str, *, buffer:bytes=None, sync_to_remote:bool):
        """Modify buffer_info to reflect that checksum is surely deserializable into celltype
        """
        # for mixed: if possible, retrieve the buffer locally to check for things like is_numpy etc.
        if not isinstance(checksum, bytes):
            raise TypeError(type(checksum))
        if celltype == "bytes":
            return
        if celltype == "checksum":
            # out-of-scope for buffer info
            return
        if celltype in ("ipython", "python", "cson", "yaml"):
            # parsability as IPython/python/cson/yaml is out-of-scope for buffer info
            celltype = "text"

        if celltype == "mixed":
            if buffer is None:
                buffer = self.get_buffer(checksum, remote=False)
            if buffer is not None:
                if buffer.startswith(MAGIC_NUMPY):
                    self.update_buffer_info(checksum, "is_numpy", True, sync_remote=False)
                elif buffer.startswith(MAGIC_SEAMLESS_MIXED):
                    self.update_buffer_info(checksum, "is_seamless_mixed", True, sync_remote=False)
                else:
                    self.update_buffer_info(checksum, "is_json", True, sync_remote=False)
            elif checksum not in self.buffer_info:
                self.buffer_info[checksum] = BufferInfo(checksum)
        elif celltype == "binary":
            self.update_buffer_info(checksum, "is_numpy", True, sync_remote=False)
        elif celltype == "plain":
            self.update_buffer_info(checksum, "is_json", True, sync_remote=False)
        elif celltype == "text":
            self.update_buffer_info(checksum, "is_utf8", True, sync_remote=False)
        elif celltype in ("str", "int", "float", "bool"):
            self.update_buffer_info(checksum, "json_type", celltype, sync_remote=False)
        else:
            raise TypeError(celltype)

        if sync_to_remote:
            self._sync_buffer_info_to_remote(checksum)

    def buffer_check(self, checksum):
        """For the communion_server..."""
        assert checksum is not None
        assert isinstance(checksum, bytes)
        assert len(checksum) == 32
        if checksum in self.buffer_cache:
            return True
        return buffer_remote.has_buffer(checksum)

    def destroy(self):
        if self.buffer_cache is None:
            return
        self.buffer_refcount.pop(bytes.fromhex(empty_dict_checksum), None)
        self.buffer_refcount.pop(bytes.fromhex(empty_list_checksum), None)        
        if len(self.buffer_refcount):
            print_warning("buffer cache, %s buffers undestroyed" % len(self.buffer_refcount))
        self.buffer_cache = None
        self.last_time = None
        self.buffer_refcount = None
        self.buffer_info = None


buffer_cache = BufferCache()

from ..protocol.calculate_checksum import checksum_cache
from .tempref import temprefmanager
from .database_client import database
from . import CacheMissError
"""Module for caching buffers in memory"""

import time
import functools
import logging

from silk.mixed import MAGIC_NUMPY, MAGIC_SEAMLESS_MIXED

import seamless
from seamless.checksum import empty_dict_checksum, empty_list_checksum
from seamless.checksum.cached_calculate_checksum import checksum_cache
from seamless import CacheMissError
from seamless import Buffer, Checksum
from seamless.checksum.buffer_info import BufferInfo

from seamless.checksum import buffer_remote


logger = logging.getLogger(__name__)


def print_info(*args):
    """Logging aid"""
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)


def print_warning(*args):
    """Logging aid"""
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)


def print_debug(*args):
    """Logging aid"""
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)


def print_error(*args):
    """Logging aid"""
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)


class BufferCache:
    """Checksum-to-buffer cache.
    Every buffer is referred to by a CacheManager (or more than one).

    Memory intensive. Like any other cache, does not persist unless offloaded.
    Buffers can be shared over the network, or offloaded to a database.
    Keys are straightforward buffer checksums.

    NOTE: if there is a database active, buffers are normally not maintained in local cache.
    Refcounts are still maintained; a buffer with a refcount is sure to have
    been written into the database

    It is always possible to cache a buffer that has no refcount into local cache for a short while
    """

    SMALL_BUFFER_LIMIT = 100000
    LIFETIME_TEMP = (
        20.0  # buffer_cache keeps unreferenced buffer values alive for 20 secs
    )
    LIFETIME_TEMP_SMALL = 600.0  # buffer_cache keeps unreferenced small buffer
    #  values (< SMALL_BUFFER_LIMIT bytes) alive for 10 minutes

    LOCAL_MODE_FULL_PERSISTENCE = (
        True  # in local mode (no delegation), buffer_cache keeps
    )
    # non-persistent buffers alive as long as they are referenced

    _bottled_update_time_calls = None

    def __init__(self):
        self.buffer_cache = {}  # local cache, checksum-to-buffer
        self.last_time = {}
        self.buffer_refcount = {}  # buffer-checksum-to-refcount
        # Buffer info cache (never expire)
        self.buffer_info = {}  # checksum-to-buffer-info
        self.synced_buffer_info = (
            set()
        )  # set of bufferinfo checksums that are in-sync with the database
        self.missing = {}  # key: checksum, value: persistent (bool)
        self.persistent_buffers = (
            set()
        )  # only used if LOCAL_MODE_FULL_PERSISTENCE is False

        self._bottled_update_time_calls = []

        self.incref_buffer(Checksum(empty_dict_checksum), b"{}\n", persistent=True)
        self.incref_buffer(Checksum(empty_list_checksum), b"[]\n", persistent=True)

    def _check_delete_buffer(self, checksum: Checksum):
        from seamless.workflow.tempref import temprefmanager

        if checksum not in self.last_time:
            return
        t = time.time()
        l = self.buffer_info.get(checksum, {}).get("length", 999999999)
        lifetime = (
            self.LIFETIME_TEMP_SMALL
            if l < self.SMALL_BUFFER_LIMIT
            else self.LIFETIME_TEMP
        )
        last_time = self.last_time[checksum]
        curr_lifetime = t - last_time
        if curr_lifetime < lifetime:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = max(lifetime - curr_lifetime, 1)
            temprefmanager.add_ref(func, delay, on_shutdown=False)
            return
        self._uncache_buffer(checksum)

    def _uncache_buffer(self, checksum: Checksum):
        if checksum in self.buffer_refcount:
            can_delete = True
            if self.LOCAL_MODE_FULL_PERSISTENCE or checksum in self.persistent_buffers:
                can_delete = buffer_remote.can_read_buffer(checksum)
            if not can_delete:
                return
        self.last_time.pop(checksum, None)
        self.buffer_cache.pop(checksum, None)

    def _unbottle_update_time(self):
        bottled_update_time_calls = self._bottled_update_time_calls.copy()
        self._bottled_update_time_calls.clear()
        for checksum, buffer_length in bottled_update_time_calls:
            self._do_update_time(checksum, buffer_length)

    def _update_time(self, checksum: Checksum, buffer_length: int | None = None):
        if not seamless.SEAMLESS_WORKFLOW_IMPORTED:
            self._bottled_update_time_calls.append((checksum, buffer_length))
            return
        else:
            return self._do_update_time(checksum, buffer_length)

    def _do_update_time(self, checksum: Checksum, buffer_length: int | None = None):
        from seamless.workflow.tempref import temprefmanager

        t = time.time()
        if buffer_length is None:
            buffer_length = 9999999
        if checksum not in self.last_time:
            func = functools.partial(self._check_delete_buffer, checksum)
            delay = (
                self.LIFETIME_TEMP_SMALL
                if buffer_length < self.SMALL_BUFFER_LIMIT
                else self.LIFETIME_TEMP
            )
            temprefmanager.add_ref(func, delay, on_shutdown=False)
        self.last_time[checksum] = t

    def cache_buffer(self, checksum: Checksum, buffer: Buffer):
        """Caches a buffer locally for a short time, without incrementing its refcount
        Does not write it as remote server or buffer.
        The checksum can be incref'ed later, without the need to re-provide the buffer.

        NOTE: seamless.workflow is needed to remove zero-refcount buffers after a short while.
        As long as seamless.workflow has not yet been imported, these buffers will accumulate
        in memory.
        """
        if not checksum:
            return
        checksum = Checksum(checksum)
        buffer = Buffer(buffer, checksum=checksum)
        # print("LOCAL CACHE", checksum.hex())
        self._update_time(checksum, len(buffer))
        self.update_buffer_info(checksum, "length", len(buffer), sync_remote=False)
        if not buffer_remote.is_known(checksum):
            self.buffer_cache[checksum] = buffer
        self.find_missing(checksum, buffer)

    def incref_buffer(self, checksum: Checksum, buffer: Buffer, *, persistent):
        """Increments the refcount of a known buffer.
        See the documentation of self.incref.
        """
        assert checksum
        checksum = Checksum(checksum)
        buffer = Buffer(buffer)
        l = len(buffer)
        self.update_buffer_info(checksum, "length", l, sync_remote=False)
        return self._incref([checksum], persistent, [buffer])

    def find_missing(self, checksum, buffer, persistent=False):
        """If a checksum is among the missing buffers, try to find it
        and remove it from the missing buffers."""
        if checksum in self.missing:
            if buffer is None:
                buffer = self.buffer_cache.get(checksum)
            if buffer is not None:
                if isinstance(buffer, Buffer):
                    buffer = buffer.value
                assert isinstance(buffer, bytes)
                print_debug("Found missing buffer: {}".format(checksum.hex()))
                if self.missing.pop(checksum):
                    persistent = True
                if persistent and not buffer_remote.is_known(checksum):
                    if buffer_remote.can_write():
                        buffer_remote.write_buffer(checksum, buffer)
                    else:
                        self.buffer_cache[checksum] = buffer
                else:
                    self.cache_buffer(checksum, buffer)

    def _incref(self, checksums, persistent, buffers):
        for n, checksum in enumerate(checksums):
            if checksum.hex() in (empty_dict_checksum, empty_list_checksum):
                continue
            buffer = None
            if buffers is not None:
                buffer = buffers[n]

            """
            print(
                "INCREF     ",
                checksum.hex(),
                persistent,
                buffer is None,
                checksum in self.missing,
            )
            """
            if persistent and not self.LOCAL_MODE_FULL_PERSISTENCE:
                self.persistent_buffers.add(checksum)
            if checksum in self.buffer_refcount:
                self.buffer_refcount[checksum] += 1
            else:
                self.buffer_refcount[checksum] = 1
            if buffer is None:
                buffer = self.buffer_cache.get(checksum)
            if buffer is not None:
                self.find_missing(checksum, buffer)
                if persistent and not buffer_remote.is_known(checksum):
                    if buffer_remote.can_write():
                        buffer_remote.write_buffer(checksum, buffer)
                    else:
                        self.buffer_cache[checksum] = buffer
                else:
                    self.cache_buffer(checksum, buffer)
            else:
                if not buffer_remote.is_known(checksum):
                    if n < 10:
                        print_debug(
                            "Incref checksum of missing buffer: {}".format(
                                checksum.hex()
                            )
                        )
                    elif n == 10:
                        print_debug("... ({} more buffers)".format(len(checksums) - 10))
                    if persistent:
                        self.missing[checksum] = True
                    elif checksum not in self.missing:
                        self.missing[checksum] = False
            # print("/INCREF")

    def incref(self, checksum: Checksum, *, persistent):
        """Increments the refcount of a buffer checksum.

        If the buffer cannot be retrieved, it is registered as missing.
        Otherwise, it is moved from local cache into the database.
        If there is no database, it will remain in local cache for a short while.
        """
        checksum = Checksum(checksum)
        assert checksum
        buffer = None
        if checksum not in self.buffer_refcount:
            buffer = self.buffer_cache.get(checksum)
        self._incref([checksum], persistent, [buffer])

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
                self.missing.pop(checksum, None)
                # print("DESTROY", checksum.hex(), can_delete, checksum in self.buffer_cache)
                if checksum in self.buffer_cache:
                    buffer = self.get_buffer(checksum)
                    if buffer is not None:  # should be ok normally
                        self.cache_buffer(checksum, buffer)

    def decref(self, checksum: Checksum):
        """Decrements the refcount of a buffer checksum, cached with incref_buffer
        If the refcount reaches zero, and there is no remote buffer storage,
         it will be added to local cache using cache_buffer.
        This means that it will remain accessible for a short while
        """
        checksum = Checksum(checksum)
        assert checksum
        # print("DECREF     ", checksum)
        return self._decref([checksum])

    def get_buffer(
        self, checksum: Checksum, *, remote: bool = True, deep: bool = False
    ):
        """Retrieve a buffer from cache.
        If remote=True:
            - Try to download it from buffer read servers/folders
            - Try to download it via the FAIR client or direct URLs.
        If deep=True, the buffer is a deep buffer.
          This does not affect the result, but it does affect how
          FAIR servers are interrogated.
        """
        from seamless import fair

        checksum = Checksum(checksum)
        if not checksum:
            return None
        if checksum.hex() == empty_dict_checksum:
            return b"{}\n"
        elif checksum.hex() == empty_list_checksum:
            return b"[]\n"
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            if isinstance(buffer, Buffer):
                buffer = buffer.value
            assert isinstance(buffer, bytes), type(buffer)
            return buffer
        buffer = self.buffer_cache.get(checksum)
        if buffer is not None:
            if isinstance(buffer, Buffer):
                buffer = buffer.value
            assert isinstance(buffer, bytes), type(buffer)
            return buffer
        if remote:
            try:
                buffer = buffer_remote.get_buffer(checksum)
            except Exception:
                import traceback

                traceback.print_exc()
            if buffer is not None:
                if isinstance(buffer, Buffer):
                    buffer = buffer.value
                assert isinstance(buffer, bytes), type(buffer)
            else:
                # fair.get_buffer may download the buffer using the .access method
                buffer = fair.get_buffer(checksum, deep=deep)
                if buffer is not None:
                    if isinstance(buffer, Buffer):
                        buffer = buffer.value
                    assert isinstance(buffer, bytes), type(buffer)
                    buffer_cache.cache_buffer(checksum, buffer)
                    return buffer

        return buffer

    def _sync_buffer_info_from_remote(self, checksum):
        from seamless.checksum.database_client import database

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
        from seamless.checksum.database_client import database

        local_buffer_info = self.buffer_info[checksum]
        if checksum in self.synced_buffer_info:
            return
        database.set_buffer_info(checksum, local_buffer_info)
        self.synced_buffer_info.add(checksum)

    def get_buffer_info(
        self,
        checksum: Checksum,
        *,
        sync_remote: bool,
        buffer_from_remote: bool,
        force_length: bool
    ) -> BufferInfo | None:
        """Try to retrieve BufferInfo from cache.
        If sync_remote, bidirectionally synchronize the BufferInfo with the Seamless database.
          BufferInfo from the database has precedence over locally known information.
        If force_length, return a BufferInfo with at least the length, or raise an Exception.
          To obtain the length, the buffer itself may be obtained.
        If force_length and buffer_from_remote, try to download the buffer remotely
          if its length is unknown and it cannot be obtained locally.
        """
        checksum = Checksum(checksum)
        if not checksum:
            return None
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
                    checksum,
                    "length",
                    length,
                    sync_remote=sync_remote,
                    no_sync_from_remote=True,
                )
                break
        else:
            raise CacheMissError(checksum.hex())

        return buffer_info

    def update_buffer_info_conversion(
        self,
        checksum,
        source_celltype,
        target_checksum,
        target_celltype,
        *,
        sync_remote
    ):
        """Update BufferInfo, registering a conversion as possible.
        If connected, update the database."""
        field = None
        if source_celltype == "str" and target_celltype == "text":
            field = "str2text"
        elif source_celltype == "text" and target_celltype == "str":
            field = "text2str"
        elif source_celltype == "binary" and target_celltype == "bytes":
            field = "binary2bytes"
        elif source_celltype == "bytes" and target_celltype == "binary":
            field = "bytes2binary"
        elif source_celltype == "binary" and target_celltype == "plain":
            field = "binary2json"
        elif source_celltype == "plain" and target_celltype == "binary":
            field = "json2binary"

        if field is None:
            return

        buffer_info = self.buffer_info.get(checksum)
        if buffer_info is None:
            buffer_info = BufferInfo(checksum)
            self.buffer_info[checksum] = buffer_info
        if sync_remote and checksum not in self.synced_buffer_info:
            self._sync_buffer_info_from_remote(checksum)
        if buffer_info[field] == target_checksum:
            return
        self.synced_buffer_info.discard(checksum)
        buffer_info[field] = target_checksum
        if sync_remote:
            self._sync_buffer_info_to_remote(checksum)

    def update_buffer_info(
        self, checksum, attr, value, *, sync_remote, no_sync_from_remote=False
    ):
        """Update BufferInfo.
        If sync_remote, synchronize to the database.
        If not no_sync_from_remote, synchronize from the database as well."""
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
        if (
            sync_remote
            and (not no_sync_from_remote)
            and checksum not in self.synced_buffer_info
        ):
            self._sync_buffer_info_from_remote(checksum)
        if buffer_info[attr] != value:
            self.synced_buffer_info.discard(checksum)
        buffer_info[attr] = value
        if value:
            for f in co_flags.get(attr, []):
                self.update_buffer_info(checksum, f, True, sync_remote=False)
            for f in anti_flags.get(attr, []):
                self.update_buffer_info(checksum, f, False, sync_remote=False)
        elif value == False:  # pylint: disable=singleton-comparison
            for f in co_flags.get(attr, []):
                self.update_buffer_info(checksum, f, False, sync_remote=False)
        if sync_remote:
            self._sync_buffer_info_to_remote(checksum)

    def guarantee_buffer_info(
        self,
        checksum: Checksum,
        celltype: str,
        *,
        buffer: bytes = None,
        sync_to_remote: bool
    ):
        """Modify buffer_info to reflect that checksum is surely deserializable into celltype"""
        # for mixed: if possible, retrieve the buffer locally to check for things like is_numpy etc.
        checksum = Checksum(checksum)
        if not checksum:
            raise ValueError(None)
        if celltype == "bytes":
            return
        if celltype == "checksum":
            # out-of-scope for buffer info
            return
        if celltype in ("ipython", "python", "cson", "yaml"):
            # parsability as IPython/python/cson/yaml is out-of-scope for buffer info
            celltype = "text"

        if checksum not in self.buffer_info:
            if buffer is None:
                buffer = self.get_buffer(checksum, remote=False)
            if buffer is not None:
                self.buffer_info[checksum] = BufferInfo(
                    checksum, {"length": len(buffer)}
                )

        if celltype == "mixed":
            if buffer is None:
                buffer = self.get_buffer(checksum, remote=False)
            if buffer is not None:
                if buffer.startswith(MAGIC_NUMPY):
                    self.update_buffer_info(
                        checksum, "is_numpy", True, sync_remote=False
                    )
                elif buffer.startswith(MAGIC_SEAMLESS_MIXED):
                    self.update_buffer_info(
                        checksum, "is_seamless_mixed", True, sync_remote=False
                    )
                else:
                    self.update_buffer_info(
                        checksum, "is_json", True, sync_remote=False
                    )
        elif celltype == "binary":
            self.update_buffer_info(checksum, "is_numpy", True, sync_remote=False)
        elif celltype == "plain":
            self.update_buffer_info(checksum, "is_json", True, sync_remote=False)
        elif celltype == "text":
            self.update_buffer_info(checksum, "is_utf8", True, sync_remote=False)
        elif celltype in ("str", "int", "float", "bool"):
            self.update_buffer_info(checksum, "json_type", celltype, sync_remote=False)
        elif celltype is None:
            pass
        else:
            raise TypeError(celltype)

        if sync_to_remote and checksum in self.buffer_info:
            self._sync_buffer_info_to_remote(checksum)

    def buffer_check(self, checksum: Checksum) -> bool:
        """Check if the buffer is available,
        either in local cache or remotely."""
        checksum = Checksum(checksum)
        assert checksum
        if checksum in self.buffer_cache:
            return True
        return buffer_remote.can_read_buffer(checksum)

    def destroy(self):
        """Uncache all cached buffers"""
        if self.buffer_cache is None:
            return
        self.buffer_refcount.pop(empty_dict_checksum, None)
        self.buffer_refcount.pop(empty_list_checksum, None)
        if len(self.buffer_refcount):
            print_warning(
                "buffer cache, %s buffers undestroyed" % len(self.buffer_refcount)
            )
        self.buffer_cache = None
        self.last_time = None
        self.buffer_refcount = None
        self.buffer_info = None


buffer_cache = BufferCache()

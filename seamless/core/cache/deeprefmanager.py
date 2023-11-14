import asyncio
import traceback
from weakref import WeakSet

from ... import calculate_dict_checksum
from ..status import StatusReasonEnum
from ..cache.buffer_cache import buffer_cache, empty_dict_checksum, empty_list_checksum
from ..cache import CacheMissError

_rev_cs_hashpattern = {}

class DeepRefManager:
    MAX_DEEP_BUFFER_SIZE = 10**9       # Don't incref member buffers inside a deep buffer larger than this
    MAX_DEEP_BUFFER_MEMBERS = 100000   # Don't incref member buffers inside a deep buffer with more members than this

    def __init__(self):
        self.buffers_to_incref = set()
        self.checksum_to_cell = {}
        self.checksum_to_subchecksums = {}
        self.refcount = {}
        self.big_buffers = set()
        self.invalid_deep_buffers = set()
        self.missing_deep_buffers = set()
        self._destroyed = False
        self.runner = asyncio.ensure_future(self.run())
        self.coros = {}

    def _invalidate(self, checksum, hash_pattern, exc):
        self.invalid_deep_buffers.add((checksum, calculate_dict_checksum(hash_pattern)))
        # crude, but hard to do otherwise
        for cell in self.checksum_to_cell.get(checksum, WeakSet()):
            manager = cell._get_manager()
            if manager is None or manager._destroyed:
                continue
            if cell._structured_cell is None or cell._structured_cell.schema is cell:
                manager.cancel_cell(cell, void=True)
            else:
                sc = cell._structured_cell
                sc._exception = str(exc)
                manager._set_cell_checksum(sc._data, None, void=True, status_reason=StatusReasonEnum.INVALID)
                manager.structured_cell_trigger(sc, void=True)


    def _do_incref(self, checksum, deep_structure, hash_pattern):
        try:
            sub_checksums = deep_structure_to_checksums(
                deep_structure, hash_pattern
            )
            buffer_cache.update_buffer_info(checksum, "members", len(sub_checksums), sync_remote=False)
            if len(sub_checksums) > self.MAX_DEEP_BUFFER_MEMBERS:
                self.big_buffers.add(checksum)
                return
            sub_checksums2 = [bytes.fromhex(cs) for cs in sub_checksums]
            #print("INC DEEP", checksum.hex(), len(sub_checksums))
            buffer_cache._incref(sub_checksums2, persistent=True, buffers=None)
            refcount = self.refcount.get(checksum, 0)
            if refcount > 0:
                assert checksum in self.checksum_to_subchecksums, checksum.hex()
            else:
                self.checksum_to_subchecksums[checksum] = sub_checksums2
            self.refcount[checksum] = refcount + 1
        except Exception as exc:
            self._invalidate(checksum, hash_pattern, exc)
        finally:
            self.checksum_to_cell.pop(checksum, None)

    async def _run_once(self):

        def new_coro_2(key, deep_buffer):
            checksum, _ = key
            new_coro = asyncio.ensure_future(deserialize(deep_buffer, checksum, "mixed", False))
            new_coro_entry = 2, key, new_coro 
            self.coros[key] = new_coro_entry

        for key in list(self.buffers_to_incref):
            if key in self.coros:
                continue
            checksum, _ = key
            """
            # TODO: "get_buffer_database" where the database buffer request is done async
            """
            deep_buffer = get_buffer(checksum, remote=True)
            if deep_buffer is None:
                self.missing_deep_buffers.add(checksum)
                self.buffers_to_incref.remove(key)
                continue
            self.missing_deep_buffers.discard(checksum)
            new_coro_2(key, deep_buffer)
            
        def invalidate(checksum, exc):
            for key in list(self.buffers_to_incref):
                if key[0] == checksum:
                    hash_pattern = _rev_cs_hashpattern[key[1]]
                    self._invalidate(checksum, hash_pattern, exc)

        if not self.coros:
            await asyncio.sleep(0.01)
            return

        coros = [coro_entry[2] for coro_entry in self.coros.values()]
        done, _ = await asyncio.wait(coros, return_when=asyncio.FIRST_COMPLETED)
        for coro in done:
            for coro_entry in list(self.coros.values()):
                mode, key, coro0 = coro_entry
                if coro0 is coro:
                    self.coros.pop(key)
                    exc = coro.exception()
                    if isinstance(exc, KeyboardInterrupt):
                        raise exc from None
                    checksum, _ = key
                    if mode == 1:
                        # mode == 1 is not being useed at the time
                        if exc is not None:
                            invalidate(checksum, exc)
                        else:
                            deep_buffer = coro.result()
                            if deep_buffer is None:
                                raise CacheMissError(checksum.hex())
                            new_coro_2(key, deep_buffer)
                    else: # mode == 2
                        if exc is not None:
                            invalidate(checksum, exc)
                        else:
                            deep_structure = coro.result()
                            for key in list(self.buffers_to_incref):
                                if key[0] == checksum:
                                    hash_pattern = _rev_cs_hashpattern[key[1]]
                                    self.buffers_to_incref.remove(key)
                                    hpcs = calculate_dict_checksum(hash_pattern)
                                    _rev_cs_hashpattern[hpcs] = hash_pattern
                                    e = (checksum, hpcs)
                                    if e in self.invalid_deep_buffers:
                                        continue
                                    self._do_incref(checksum, deep_structure,hash_pattern)

                    break


    async def run(self):
        from seamless import SEAMLESS_FRUGAL
        exc_count = 0
        while not self._destroyed:
            try:
                await self._run_once()
            except Exception:
                exc_count += 1
                if exc_count <= 5:
                    traceback.print_exc()
            if SEAMLESS_FRUGAL:
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(0.001)

    @property
    def busy(self):
        return (len(self.buffers_to_incref) > 0)

    def destroy(self):
        self._destroyed = True

    def incref_deep_buffer(self, checksum, hash_pattern, *, cell=None):
        if checksum.hex() in (empty_dict_checksum, empty_list_checksum):
            return
        if checksum in self.big_buffers:
            return
        hpcs = calculate_dict_checksum(hash_pattern)
        _rev_cs_hashpattern[hpcs] = hash_pattern
        key = (checksum, hpcs)
        
        if key not in self.buffers_to_incref:
            try:
                deep_buffer_info = buffer_cache.get_buffer_info(checksum, sync_remote=True, buffer_from_remote=False, force_length=False)
                if deep_buffer_info.members is not None and deep_buffer_info.members > self.MAX_DEEP_BUFFER_MEMBERS:
                    self.big_buffers.add(checksum)
                    return
                deep_buffer_info = buffer_cache.get_buffer_info(checksum, sync_remote=False, buffer_from_remote=True, force_length=True)
                if deep_buffer_info.length > self.MAX_DEEP_BUFFER_SIZE:
                    self.big_buffers.add(checksum)
                    return
            except CacheMissError as exc:
                self._invalidate(checksum, hash_pattern, exc)
                return
            self.buffers_to_incref.add(key)
        if cell is not None:
            cells = self.checksum_to_cell.get(checksum)
            if cells is None:
                cells = WeakSet()
                self.checksum_to_cell[checksum] = cells
            cells.add(cell)

    def decref_deep_buffer(self, checksum, hash_pattern):
        from seamless.util import is_forked
        if is_forked():
            return
        if checksum.hex() in (empty_dict_checksum, empty_list_checksum):
            return
        if checksum in self.big_buffers:
            return
        if (checksum, calculate_dict_checksum(hash_pattern)) in self.invalid_deep_buffers:
            return
        hpcs = calculate_dict_checksum(hash_pattern)
        _rev_cs_hashpattern[hpcs] = hash_pattern
        key = (checksum, hpcs)
        if key in self.buffers_to_incref:
            self.buffers_to_incref.remove(key)
            return

        if checksum not in self.missing_deep_buffers:
            assert checksum in self.checksum_to_subchecksums, checksum.hex()
            sub_checksums = self.checksum_to_subchecksums[checksum]
            buffer_cache._decref(sub_checksums)
            refcount = self.refcount.pop(checksum) - 1
            if refcount > 0:
                self.refcount[checksum] = refcount
            else:
                self.checksum_to_subchecksums.pop(checksum)

deeprefmanager = DeepRefManager()

from ..protocol.deep_structure import deep_structure_to_checksums
from ..protocol.deserialize import deserialize
from ..protocol.get_buffer import get_buffer

from weakref import WeakValueDictionary, WeakKeyDictionary, WeakSet, ref
from collections import deque, OrderedDict
from speg.peg import ParseError
import sys, os
import time
import traceback
import copy
from contextlib import contextmanager
import json
import itertools
import functools
import asyncio

from ..get_hash import get_hash

import logging
logger = logging.getLogger("seamless")

def get_fallback_checksum(cell):
    manager = cell._get_manager()
    fallback = manager.get_fallback(cell)
    if fallback is None:
        return cell._checksum
    else:
        return fallback._checksum

class ShareItem:
    last_exc = None
    _destroyed = False
    _initialized = False
    _initializing = False
    _cellname = None
    share = None
    def __init__(self, cell, path, readonly, *,
        mimetype=None,
        toplevel=False,  # if True, don't use the name of the namespace, but serve under the web root directly
        cellname=None
    ):
        self.path = path
        self.celltype = cell._celltype
        self.cell = ref(cell)
        assert isinstance(readonly, bool)
        self.readonly = readonly
        self.mimetype = mimetype
        self.toplevel = toplevel
        self._cellname = cellname

    @property
    def cellname(self):
        if self._cellname is not None:
            return self._cellname
        cell = self.cell()
        if cell is None:
            return None
        return cell._format_path()


    def init(self):
        if self._initialized:
            return
        if self._initializing:
            return
        if self._destroyed:
            return
        cell = self.cell()
        if cell is None:
            return
        if cell._destroyed:
            return
        if not self.readonly:
            assert cell.has_independence(), cell # mount read mode only for authoritative cells
        self._initializing = True
        try:
            manager = cell._get_manager()
            name = shareserver.manager_to_ns.get(manager)
            if name is None:
                msg = "Cannot bind %s to share path %s: manager is not shared"
                raise Exception(msg % (cell, self.path))
            self._namespace = name

            cell_checksum = get_fallback_checksum(cell)
            cell_pending = manager.taskmanager.is_pending(cell)
            cell_empty = (cell_checksum is None)
            _, cached_share = sharemanager.cached_shares.get((name, self.path), (None, None))
            from_cache = False
            if cached_share is not None:
                if cell_empty and not self.readonly:
                    cell_checksum = cached_share._checksum
                    from_cache = True
                for attr in ("readonly", "celltype", "mimetype"):
                    if getattr(cached_share, attr) != getattr(self, attr):
                        cached_share = None
                        break
            if cached_share is not None:
                sharemanager.cached_shares.pop((name, self.path))
                self.share = cached_share
            else:
                namespace = shareserver.namespaces[name]
                self.share = namespace.add_share(
                    self.path, self.readonly,
                    self.celltype, self.mimetype
                )
            self.share.bind(self)
            if from_cache and not cell_pending:
                self.update(cell_checksum)
        finally:
            self._initialized = True
            self._initializing = False

    async def write(self):
        cell = self.cell()
        if cell is None:
            return
        if cell._destroyed:
            return
        while self._initializing:
            await asyncio.sleep(0.01)
        if self.share is not None:
            manager = cell._get_manager()
            cell_pending = manager.taskmanager.is_pending(cell)
            if not cell_pending:
                # If the cell is pending, a running task will later call manager._set_cell_checksum,
                #   which will call sharemanager.add_cell_update, which will call us again
                self.share.set_checksum(get_fallback_checksum(cell))

    def update(self, checksum):
        # called by shareserver, or from init
        assert checksum is None or isinstance(checksum, bytes)
        if not self.readonly:
            sharemanager.share_value_updates[self] = checksum

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.share is not None:
            self.share.unbind()
            now = time.time()
            sharemanager.cached_shares[self._namespace, self.path] = (now, self.share)

    def __del__(self):
        if self._destroyed:
            return
        self._destroyed = True
        logger.warning("undestroyed mount path %s" % self.path)
        #self.destroy()


class ShareManager:
    GARBAGE_DELAY = 20
    _running = False
    _last_run = None
    _stop = False
    _future_run = None
    _current_run = None
    def __init__(self, latency):
        self.latency = latency
        self.shares = {}
        self.cell_updates = {}
        self.share_updates = set()
        self.share_value_updates = {}
        self.paths = {}
        self.cached_shares = {} # key: namespace, file path; value: (deletion time, share.Share)

    def new_namespace(self, manager, share_evaluate, name=None):
        from .manager import Manager
        assert isinstance(manager, Manager)
        self.paths[manager] = set()
        name = shareserver._new_namespace(manager, share_evaluate, name)
        return name


    def unshare(self, cell, from_del=False):
        manager = cell._get_manager()
        if from_del and (cell not in self.shares or manager not in self.paths):
            return
        if cell not in self.shares and cell in self.share_updates:
            return
        share_item = self.shares.pop(cell)
        if not share_item._destroyed:
            paths = self.paths[manager]
            path = share_item.path
            paths.discard(path)
            share_item.destroy()

    def update_share(self, cell):
        self.start()
        self.share_updates.add(cell)

    def add_cell_update(self, cell, checksum):
        if cell in self.share_updates:
            return
        assert cell in self.shares, (cell, hex(id(cell)))
        self.cell_updates[cell] = checksum

    async def run_once(self):

        for cell in self.share_updates:
            if cell._destroyed:
                continue
            share_params = cell._share
            share_item = self.shares.get(cell)
            if share_params is None and share_item is None:
                continue
            if share_params is not None:
                path = share_params["path"]
                if path is None:
                    path = "/".join(cell.path)
                readonly = share_params["readonly"]
                if share_item is not None:
                    if share_item.path == path and \
                      share_item.readonly == readonly:
                        continue
            if share_item is not None:
                self.shares.pop(cell)
                share_item.destroy()
            if share_params is not None:
                mimetype = share_params.get("mimetype")
                toplevel = share_params.get("toplevel", False)
                cellname = share_params.get("cellname")
                new_share_item = ShareItem(
                    cell, path, readonly, mimetype=mimetype,
                    toplevel=toplevel,
                    cellname=cellname
                )
                self.shares[cell] = new_share_item
                checksum = get_fallback_checksum(cell)
                if checksum is not None:
                    self.cell_updates[cell] = checksum
        self.share_updates.clear()

        for share_item in self.shares.values():
            try:
                share_item.init()
            except:
                traceback.print_exc()

        cell_updates = {cell: checksum \
            for cell, checksum in self.cell_updates.items()}
        self.cell_updates.clear()

        value_updates = list(self.share_value_updates.items())
        self.share_value_updates.clear()
        for share_item, checksum in value_updates:
            cell = share_item.cell()
            if cell is None:
                continue
            if cell._destroyed:
                continue
            if cell in cell_updates:
                continue
            from_buffer = False
            if checksum is not None and cell._celltype in ("plain", "mixed"):
                try:
                    buffer = get_buffer(checksum)
                except CacheMissError:
                    buffer = await get_buffer_remote(
                        checksum,
                        None
                    )
                if buffer is not None:
                    try:
                        checksum = await conversion(checksum, "cson", "plain", buffer=buffer)
                    except ValueError:
                        from_buffer = True
            if from_buffer:
                cell.set_buffer(buffer, checksum)
            else:
                if checksum is not None:
                    checksum = checksum.hex()
                cell.set_checksum(checksum)
        self.share_value_updates.clear()

        for cell, checksum in cell_updates.items():
            if cell._destroyed:
                continue
            try:
                share_item = self.shares[cell]
                if not share_item._initialized:
                    share_item.init()
                else:
                    await share_item.write()
            except:
                traceback.print_exc()

        now = time.time()
        to_destroy = []
        for npath, value in self.cached_shares.items():
            mod_time, share = value
            if now > mod_time + self.GARBAGE_DELAY:
                to_destroy.append(npath)
        for npath in to_destroy:
            mod_time, share = self.cached_shares.pop(npath)
            share.destroy()

    async def _run(self):
        try:
            self._running = True
            while not self._stop:
                t = time.time()
                try:
                    if self._current_run is None:
                        self._current_run = asyncio.ensure_future(self.run_once())
                    await self._current_run
                except Exception:
                    import traceback
                    traceback.print_exc()
                finally:
                    self._current_run = None
                while time.time() - t < self.latency:
                    await asyncio.sleep(0.05)
        finally:
            self._running = False

    def start(self):
        if self._running:
            return
        if self._future_run is None:
            self._future_run = asyncio.ensure_future(self._run())
        return self._future_run

    async def _await_stop(self):
        while self._running:
            await asyncio.sleep(0.01)

    def stop(self):
        self._stop = True
        fut = asyncio.ensure_future(self._await_stop())
        asyncio.get_event_loop().run_until_complete(fut)

    async def tick_async(self):
        """Waits until one iteration of the run() loop has finished"""
        if self._current_run is None:
            self._current_run = asyncio.ensure_future(self.run_once())
        await self._current_run

    def tick(self):
        """Waits until one iteration of the run() loop has finished"""
        if self._current_run is None:
            self._current_run = asyncio.ensure_future(self.run_once())
        asyncio.get_event_loop().run_until_complete(self._current_run)

sharemanager = ShareManager(0.2)

from ..shareserver import shareserver
from .protocol.get_buffer import get_buffer, get_buffer_remote, CacheMissError
from ..core.protocol.evaluate import conversion
from .protocol.calculate_checksum import calculate_checksum
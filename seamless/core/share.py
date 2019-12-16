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

import sys
def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

class ShareItem:
    last_exc = None
    _destroyed = False
    _initialized = False
    _initializing = False
    def __init__(self, cell, path, readonly):
        self.path = path
        self.cell = ref(cell)
        assert isinstance(readonly, bool)
        self.readonly = readonly

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
            assert cell.has_authority(), cell # mount read mode only for authoritative cells
        self._initializing = True
        try:
            cell_checksum = cell._checksum
            cell_empty = (cell_checksum is None)
            _, cached_share = sharemanager.cached_shares.get(self.path, (None, None))
            from_cache = False
            if cached_share is not None:
                if cell_empty and not self.readonly:
                    cell_checksum = cached_share._checksum
                    from_cache = True
            if cached_share is not None:
                namespace = cached_share.namespace()
                root = namespace._ctx_root()            
                if root is not cell._root():
                    msg = "Cannot re-bind %s to share path %s: was bound to a different root context"
                    raise Exception(msg % (self.cell, self.path)) 
                self.share = cached_share
            else:
                root = cell._root()
                name = shareserver.root_to_ns.get(root)
                if name is None:
                    msg = "Cannot bind %s to share path %s: root context is not shared"
                    raise Exception(msg % (self.cell, self.path))
                namespace = shareserver.namespaces[name]
                self.share = namespace.add_share(self.path, self.readonly)
            self.share.bind(self)
            if from_cache:
                self.update(cached_share._checksum)
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
        self.share.set_checksum(cell._checksum)

    def update(self, checksum):        
        # called by shareserver, or from init
        sharemanager.share_value_updates[self] = checksum

    def destroy(self):
        if self._destroyed:
            return        
        self._destroyed = True
        self.share.unbind()            
        now = time.time()
        sharemanager.cached_shares[self.path] = (now, self.share)

    def __del__(self):
        if self._destroyed:
            return
        self._destroyed = True
        log("undestroyed mount path %s" % self.path)
        #self.destroy()


class ShareManager:
    GARBAGE_DELAY = 20
    _running = False
    _last_run = None
    _stop = False
    def __init__(self, latency):
        self.latency = latency
        self.shares = {}
        self.cell_updates = {}
        self.share_updates = set()
        self.share_value_updates = {}
        self._tick = False
        self.paths = {}
        self.cached_shares = {} # key: file path; value: (deletion time, share.Share)

    def new_namespace(self, ctx, share_equilibrate, name=None):
        from .unbound_context import UnboundContext
        from .context import Context
        if isinstance(ctx, UnboundContext):
            ctx = ctx._bound
        assert isinstance(ctx, Context)
        assert ctx._toplevel
        self.paths[ctx] = set()
        name = shareserver._new_namespace(ctx, share_equilibrate, name)
        return name

    def _add_share(self, cell, path, readonly):
        root = cell._root()
        if root not in self.paths:
            paths = set()
            self.paths[root] = paths
        else:
            paths = self.paths[root]
        assert path not in paths, path
        #print("add mount", path, cell)
        paths.add(path)
        item = ShareItem(cell, path, readonly)
        self.shares[cell] = item
        return item

    def unshare(self, cell, from_del=False):
        root = cell._root()
        if from_del and (cell not in self.shares or root not in self.paths):
            return
        if cell not in self.shares and cell in self.share_updates:
            return
        share_item = self.shares.pop(cell)
        if not share_item._destroyed:
            paths = self.paths[root]
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
                new_share_item = ShareItem(cell, path, readonly)
                self.shares[cell] = new_share_item
                checksum = cell._checksum
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
                buffer = await get_buffer(checksum, buffer_cache)                       
                if buffer is not None:                    
                    try:
                        checksum = await convert(checksum, buffer, "cson", "plain")
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
                if share_item.readonly:
                    continue
                share_item.init()
                await share_item.write()
            except:
                traceback.print_exc()
            
        now = time.time()
        to_destroy = []
        for path, value in self.cached_shares.items():
            mod_time, share = value
            if now > mod_time + self.GARBAGE_DELAY:
                to_destroy.append(path)
        for path in to_destroy:
            mod_time, share = self.cached_shares.pop(path)
            share.destroy()

        self._tick = True

    async def _run(self):
        try:
            self._running = True
            while not self._stop:
                t = time.time()
                try:
                    await self.run_once()
                except Exception:
                    self._tick = True
                    import traceback
                    traceback.print_exc()
                while time.time() - t < self.latency:
                    await asyncio.sleep(0.05)
        finally:
            self._running = False

    def start(self):
        if self._running:
            return
        self._future_run = asyncio.ensure_future(self._run())
        return self._future_run

    async def _await_stop(self):
        while self._running:
            await asyncio.sleep(0.01)

    def stop(self):
        self._stop = True
        fut = asyncio.ensure_future(self._await_stop())
        asyncio.get_event_loop().run_until_complete(fut)

    async def _await_tick(self):
        self._tick = False
        while self._running and not self._tick:
            await asyncio.sleep(0.01)

    def tick(self):
        """Waits until one iteration of the run() loop has finished"""
        fut = asyncio.ensure_future(self._await_tick())
        asyncio.get_event_loop().run_until_complete(fut)

sharemanager = ShareManager(0.2)

from ..shareserver import shareserver
from .protocol.get_buffer import get_buffer
from .protocol.conversion import convert
from .protocol.calculate_checksum import calculate_checksum
from .cache.buffer_cache import buffer_cache
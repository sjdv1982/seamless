"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

manager.set_cell and manager.pin_send_update are thread-safe (can be invoked from any thread)
"""

from . import protocol
from ..mixed import MixedBase
from .cache import (CellCache, AccessorCache, TreeCache, ValueCache, 
    TransformCache, Accessor, Tree, TempRefManager, SemanticKey)

import threading
import functools
import weakref
import traceback
import contextlib

def main_thread_buffered(func):
    def main_thread_buffered_wrapper(self, *args, **kwargs):
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(func, self, *args, **kwargs)
            self.workqueue.append(work)
        else:
            func(self, *args, **kwargs)
    return main_thread_buffered_wrapper

class Manager:
    flushing = False
    def __init__(self, ctx):
        assert ctx._toplevel
        self.ctx = weakref.ref(ctx)
        self.unstable = set()
        # for now, just a single global workqueue
        from .mainloop import workqueue
        self.workqueue = workqueue
        # for now, just a single global mountmanager
        from .mount import mountmanager
        self.mountmanager = mountmanager
        # caches
        self.cell_cache = CellCache(self)
        self.accessor_cache = AccessorCache(self)
        self.tree_cache = TreeCache(self)
        self.value_cache = ValueCache(self)
        self.transform_cache = TransformCache(self)
        self.temprefmanager = TempRefManager()

    def flush(self):
        assert threading.current_thread() == threading.main_thread()
        self.flushing = True
        try:
            self.workqueue.flush()
        finally:
            self.flushing = False

    def destroy(self,from_del=False):
        if self.destroyed:
            return
        self.destroyed = True
        self.ctx().destroy(from_del=from_del)

    def get_id(self):
        self._ids += 1
        return self._ids

    def cache_tree(self, tree, buffer):
        """Generates object value cache and semantic key for tree
        Invoke this routine in cache of a partial value cache miss, i.e.
        the buffer checksum is a hit, but the semantic key is either
        unknown or has expired from object cache"""

        obj, semantic_key = protocol.evaluate_from_buffer(tree, buffer)
        self.value_cache.add_semantic_key(semantic_key, obj)
        self.tree_cache.tree_to_semantic_key[hash(tree)] = semantic_key
        return obj, semantic_key


    def get_default_accessor(self, cell):
        default_accessor = Accessor()
        default_accessor.celltype = cell._celltype
        default_accessor.storage_type = cell._storage_type
        default_accessor.cell = cell
        default_accessor.access_mode = cell._default_access_mode
        default_accessor.content_type = cell._content_type
        return default_accessor

    def register_cell(self, cell):
        if cell._celltype == "structured": raise NotImplementedError ### cache branch
        ccache = self.cell_cache
        ccache.cell_to_authority[cell] = True # upon registration, all cells are authoritative
        ccache.cell_to_accessors[cell] = []


    @main_thread_buffered
    def set_cell_checksum(self, cell, checksum):
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell]
        has_auth = (auth != False)
        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        vcache = self.value_cache
        if checksum != old_checksum:
            ccache.cell_to_authority[cell] = True
            ccache.cell_to_buffer_checksums[cell] = checksum            
            if old_checksum is not None:
                vcache.decref(old_checksum, has_auth=has_auth)            
            # We don't know the buffer value, but we don't need to
            # an incref will take place anyway, possibly on a dummy item
            # The result value will tell us if the buffer value is known
            buffer_known = vcache.incref(checksum, buffer=None, has_auth=has_auth)
            if buffer_known and not is_dummy_mount(cell._mount):
                if not get_macro_mode():
                    self.mountmanager.add_cell_update(cell)

    @main_thread_buffered
    def set_cell(self, cell, value, *, from_buffer=False):
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell]
        has_auth = (auth != False)
        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        result = protocol.deserialize(
            cell._celltype, value, from_buffer=from_buffer,
            source_access_mode = None,
            source_content_type = None
        )
        buffer, checksum, obj, semantic_checksum = result
        vcache = self.value_cache
        semantic_key = SemanticKey(
            semantic_checksum, 
            cell._default_access_mode, 
            cell._content_type,
            None
        )
        if checksum != old_checksum:
            ccache.cell_to_authority[cell] = True
            ccache.cell_to_buffer_checksums[cell] = checksum            
            if old_checksum is not None:
                vcache.decref(old_checksum, has_auth=has_auth)            
            vcache.incref(checksum, buffer, has_auth=has_auth)
            vcache.add_semantic_key(semantic_key, obj)
            default_accessor = self.get_default_accessor(cell)
            default_tree = default_accessor.to_tree(checksum)
            self.tree_cache.tree_to_semantic_key[hash(default_tree)] = semantic_key
            if not is_dummy_mount(cell._mount):
                if not get_macro_mode():
                    self.mountmanager.add_cell_update(cell)
        else:
            # Just refresh the semantic key timeout
            vcache.add_semantic_key(semantic_key, obj)
            

    @main_thread_buffered
    def touch_cell(self, cell):
        from .mount import is_dummy_mount
        if self.destroyed:
            return
        raise NotImplementedError ###cache branch
        assert isinstance(cell, Cell)
        assert cell._get_manager() is self
        ###self.cell_send_update(cell, only_text=False, origin=None)
        if not is_dummy_mount(cell._mount) and self.active:
            self.mountmanager.add_cell_update(cell)

    @main_thread_buffered
    def touch_worker(self, worker):
        if self.destroyed:
            return
        assert isinstance(worker, Worker)
        assert worker._get_manager() is self
        raise NotImplementedError ###cache branch
        worker._touch()

    def leave_macro_mode(self):
        print("TODO: Manager.leave_macro_mode")


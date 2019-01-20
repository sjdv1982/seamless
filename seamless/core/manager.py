"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

manager.set_cell and manager.pin_send_update are thread-safe (can be invoked from any thread)
"""

from . import protocol
from .protocol.deserialize import deserialize
from ..mixed import MixedBase
from .cache import (CellCache, AccessorCache, ExpressionCache, ValueCache,
    TransformCache, Accessor, Expression, TempRefManager, SemanticKey)

import threading
import functools
import weakref
import traceback
import contextlib
from collections import namedtuple

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
        self.expression_cache = ExpressionCache(self)
        self.value_cache = ValueCache(self)
        self.transform_cache = TransformCache(self)
        self.temprefmanager = TempRefManager()

        self.cell_status = {}
        self.transformer_status = {}

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

    def cache_expression(self, expression, buffer):
        """Generates object value cache and semantic key for expression
        Invoke this routine in cache of a partial value cache miss, i.e.
        the buffer checksum is a hit, but the semantic key is either
        unknown or has expired from object cache"""

        obj, semantic_key = protocol.evaluate_from_buffer(expression, buffer)
        self.value_cache.add_semantic_key(semantic_key, obj)
        self.expression_cache.expression_to_semantic_key[hash(expression)] = semantic_key
        return obj, semantic_key


    def build_expression(self, accessor):
        cell = accessor.cell
        buffer_checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if buffer_checksum is None:
            return None
        return accessor.to_expression(buffer_checksum)


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
        self.cell_status[cell] = "UNDEFINED"

    def register_transformer(self, transformer):
        tcache = self.transform_cache
        tcache.transformer_to_level0[transformer] = {}
        tcache.transformer_to_cells[transformer] = []
        self.transformer_status[transformer] = "UNCONNECTED"

    def update_transformer_status(self, transformer, pinname):
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        result = "PENDING" #TODO: overruled! Status as namedtuple...
        for pin in transformer._pins:
            if transformer._pins[pin].io == "output":
                continue
            if pin not in accessor_dict:
                result = "UNCONNECTED"
                break
            accessor = accessor_dict[pin]
            cell = accessor.cell
            if self.cell_status[cell] != "OK": #TODO: more subtle evaluation
                print("UNDEFINED", transformer, pin, cell, self.cell_status[cell])
                result = "UNDEFINED"
        old_result = self.transformer_status[transformer]
        if old_result != result:
            print("UPDATE", transformer, old_result, "=>", result)
            #TODO: propagate forward


    def _connect_cell_transformer(self, cell, pin):
        """Connects cell to transformer inputpin"""
        transformer = pin.worker_ref()
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        assert pin.name not in accessor_dict, pin #double connection
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )
        accessor = self.get_default_accessor(cell)
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
        accessor_dict[pin.name] = accessor
        self.update_transformer_status(transformer, pin.name)


        if io == "input":
            pass
        elif io == "edit":
            raise NotImplementedError ###cache branch
        elif io == "output":
            raise TypeError(io) #outputpin, cannot connect a cell to that...
        else:
            raise TypeError(io)

    def connect_cell(self, cell, other):
        from . import Transformer, Reactor, Macro
        from .cell import Cell
        from .worker import PinBase
        assert isinstance(cell, Cell)
        if isinstance(other, PinBase):
            worker = other.worker_ref()
            if isinstance(worker, Transformer):
                self._connect_cell_transformer(cell, other)
            elif isinstance(worker, Reactor):
                raise NotImplementedError ###cache branch
            elif isinstance(worker, Macro):
                raise NotImplementedError ###cache branch
            else:
                raise TypeError(type(worker))
        elif isinstance(other, Cell):
            raise NotImplementedError ###cache branch
        else:
            raise TypeError(type(other))

    def connect_pin(self, cell, other):
        raise NotImplementedError ###cache branch

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
        if checksum is None:
            self.cell_status[cell] = "UNDEFINED"
            print("TODO Manager.set_cell; propagate UNDEFINED")
        else:
            self.cell_status[cell] = "OK"
            print("TODO Manager.set_cell; propagate OK")
        #also TODO: track OVERRULED; Status as namedtuple?

    @main_thread_buffered
    def set_cell(self, cell, value, *, from_buffer=False):
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell]
        has_auth = (auth != False)
        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        result = deserialize(
            cell._celltype, cell._subcelltype, cell.path,
            value, from_buffer=from_buffer, buffer_checksum=None,
            source_access_mode=None,
            source_content_type=None
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
            default_expression = default_accessor.to_expression(checksum)
            self.expression_cache.expression_to_semantic_key[hash(default_expression)] = semantic_key
            if not is_dummy_mount(cell._mount):
                if not get_macro_mode():
                    self.mountmanager.add_cell_update(cell)
            if checksum is None:
                self.cell_status[cell] = "UNDEFINED"
                print("TODO Manager.set_cell; propagate UNDEFINED")
            else:
                self.cell_status[cell] = "OK"
                print("TODO Manager.set_cell; propagate OK")
            #also TODO: track OVERRULED; Status as namedtuple?
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


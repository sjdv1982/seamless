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
    TransformCache)

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


    @main_thread_buffered
    def set_cell(self, cell, value, *,
      from_buffer=False,
      force=False, from_pin=False, origin=None
    ):
        print("manager.set_cell, TODO")
        return ###


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

    @main_thread_buffered
    def attach_child(self, child): 
        if isinstance(child, Cell):
            if child._prelim_val is not None:
                value, from_buffer = child._prelim_val
                self.set_cell(child, value, from_buffer=from_buffer)
                child._prelim_val = None


from .context import Context
from .cell import Cell
from .worker import Worker, InputPin, EditPin, OutputPin
from .transformer import Transformer
from .structured_cell import Inchannel, Outchannel, Editchannel
from .link import Link

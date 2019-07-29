import weakref
import functools
import threading
import asyncio

def mainthread(func):
    def func2(*args, **kwargs):
        assert threading.current_thread() == threading.main_thread()
        return func(*args, **kwargs)
    functools.update_wrapper(func2, func)
    return func2

def run_in_mainthread(func):
    def func2(*args, **kwargs):
        manager = args[0]
        if threading.current_thread() != threading.main_thread():
            manager.taskmanager.add_synctask(func, args, kwargs, with_event=False)
        else:
            func(*args, **kwargs)    
    functools.update_wrapper(func2, func)
    return func2

class Manager:
    _destroyed = False
    _active = True
    def __init__(self, ctx):
        from .livegraph import LiveGraph
        from .cachemanager import CacheManager
        from .taskmanager import TaskManager
        assert ctx._toplevel
        self.ctx = weakref.ref(ctx)
        from ... import communionserver
        ###communionserver.register_manager(self)
        self.livegraph = LiveGraph(self)
        self.cachemanager = CacheManager(self)
        self.taskmanager = TaskManager(self)
        loop_run_synctasks = self.taskmanager.loop_run_synctasks()
        asyncio.ensure_future(loop_run_synctasks)

        # for now, just a single global temprefmanager
        self.temprefmanager = temprefmanager

        # for now, just a single global mountmanager
        from ..mount import mountmanager
        self.mountmanager = mountmanager
        mountmanager.start()


    ##########################################################################
    # API section I: Registration (divide among subsystems)
    ##########################################################################

    @mainthread
    def register_cell(self, cell):
        self.cachemanager.register_cell(cell)
        self.livegraph.register_cell(cell)
        self.taskmanager.register_cell(cell)

    @mainthread
    def register_structured_cell(self, structured_cell):
        self.livegraph.register_structured_cell(structured_cell)

    ##########################################################################
    # API section II: Actions
    ##########################################################################

    @mainthread
    def connect(self, source, source_subpath, target, target_subpath):
        task = UponConnectionTask(
            self, source, source_subpath, target, target_subpath
        )
        task.launch()

    @run_in_mainthread
    def set_cell_checksum(self, cell, checksum, initial, is_buffercell):
        """Setting a cell checksum.
  (This is done from the command line, usually at graph loading)
  initial=True in case of graph loading; is_buffercell=True when triggered from StructuredCell)
  If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph).
  Else, cell cannot be the .data or .buffer attribute of a StructuredCell, and cannot have any incoming connection.
  
  However, if "is_buffercell" is True, then the cell can be a .buffer attribute of a StructuredCell

  If the new checksum is None, do a cell void cancellation.  
  Else: 
    If old checksum is not None, do a cell cancellation.
    Set the cell as being non-void, set the checksum (direct attribute access), and launch a cell update task. 

        """
        sc_data = self.livegraph.datacells.get(cell) 
        sc_buf = self.livegraph.buffercells.get(cell)
        if not initial:
            assert sc_data is None
            if is_buffercell:
                if sc_buf is None:
                    raise Exception("Cell was declared to be buffercell, but it is not known as such")                
            else:
                assert self.livegraph.has_authority(cell)
                assert sc_buf is None
        if checksum is None:
            self.cancel_cell(cell, void=True)
        else:
            old_checksum = self.get_cell_checksum(cell)
            if old_checksum is not None:
                self.cancel_cell(cell, void=False)
        self._set_cell_checksum(cell, checksum, (checksum is None))

    def _set_cell_checksum(self, cell, checksum, void):
        # NOTE: Any cell task depending on the old checksum must have been canceled already
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        authority = self.livegraph.has_authority(cell)
        cachemanager = self.cachemanager
        old_checksum = cell._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, cell, authority)
        cell._checksum = checksum
        cell._void = void
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, cell, authority)
            if cell._mount is not None:
                buffer, checksum = self.get_cell_buffer_and_checksum(cell)
                self.mountmanager.add_cell_update(cell, checksum, buffer)

    @run_in_mainthread
    def set_cell(self, cell, value):
        assert self.livegraph.has_authority(cell)
        self.cancel_cell(cell, value is None)
        task = SetCellValueTask(self, cell, value)
        task.launch()

    @run_in_mainthread
    def set_cell_buffer(self, cell, buffer, checksum):
        assert self.livegraph.has_authority(cell)
        self.cancel_cell(cell, buffer is None)
        task = SetCellBufferTask(self, cell, buffer, checksum)
        task.launch()

    def _get_cell_checksum_and_void(self, cell):
        while 1:
            try:
                task = CellChecksumTask(self, cell)
                task.launch_and_await()
                break
            except asyncio.CancelledError:
                continue
        return cell._checksum, cell._void

    @mainthread
    def get_cell_checksum(self, cell):
        checksum, _ = self._get_cell_checksum_and_void(cell)
        return checksum

    @mainthread
    def get_cell_void(self, cell):
        _, void = self._get_cell_checksum_and_void(cell)
        return void

    def _get_buffer(self, checksum):
        if checksum is None:
            return None
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            return buffer
        return GetBufferTask(self, checksum).launch_and_await()

    @mainthread
    def get_cell_buffer_and_checksum(self, cell):
        checksum = self.get_cell_checksum(cell)
        buffer = self._get_buffer(checksum)
        return buffer, checksum
        
    @mainthread
    def get_cell_value(self, cell, copy):
        checksum = self.get_cell_checksum(cell)
        if checksum is None:
            return None
        celltype = cell._celltype
        subcelltype = cell._subcelltype
        cached_value = deserialize_cache.get((checksum, celltype))
        if cached_value is not None:
            return cached_value
        buffer = self._get_buffer(checksum)        
        task = DeserializeBufferTask(
            self, buffer, checksum, celltype, 
            copy=copy
        )
        value = task.launch_and_await()
        return value

    ##########################################################################
    # API section ???: Cancellation
    ##########################################################################

    @mainthread
    def cancel_cell(self, cell, void, origin_task=None):
        """Cancels all tasks depending on cell, and sets all dependencies to None. 
If void=True, all dependencies are set to void as well.
If origin_task is provided, that task is not cancelled."""
        self.taskmanager.cancel_cell(cell, origin_task=origin_task)
        if cell._checksum is None:
            if not void or cell._void:
                return
        livegraph = self.livegraph
        accessors = livegraph.cell_to_downstream[cell]
        for accessor in accessors:            
            self.cancel_accessor(accessor, void)
        self._set_cell_checksum(cell, None, void)

    @mainthread
    def cancel_accessor(self, accessor, void, origin_task=None):
        self.taskmanager.cancel_accessor(accessor, origin_task=origin_task)
        if accessor.expression is None:
            if not void or expression._void:
                return
        target = accessor.write_accessor.target
        if isinstance(target, Cell):
            return self.cancel_cell(target, void=void)
        elif isinstance(target, Worker):
            if isinstance(target, Transformer):
                return self.cancel_transformer(target, void=void)
            elif isinstance(target, Reactor):
                return self.cancel_reactor(target, void=void)

    @mainthread
    def cancel_transformer(self, reactor):
        raise NotImplementedError #livegraph branch

    @mainthread
    def cancel_reactor(self, reactor):
        raise NotImplementedError #livegraph branch

    ##########################################################################
    # API section ???: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        self.cachemanager.destroy_cell(cell)
        self.livegraph.destroy_cell(self, cell)
        self.taskmanager.destroy_cell(cell, full=True)

    @mainthread
    def destroy(self, from_del=False):
        if self._destroyed:
            return
        self._destroyed = True
        ctx = self.ctx()
        if ctx is None:
            return
        ctx.destroy()
        self.mountmanager.unmount_context(ctx, from_del=from_del, toplevel=True)
        self.cachemanager.check_destroyed()
        self.livegraph.check_destroyed()
        self.taskmanager.check_destroyed()
        self.taskmanager.destroy()

    def __del__(self):
        self.destroy(from_del=True)

from .tasks import (
    SetCellValueTask, SetCellBufferTask,
    CellChecksumTask, GetBufferTask,
    DeserializeBufferTask, UponConnectionTask
)

from ..protocol.calculate_checksum import checksum_cache
from ..protocol.deserialize import deserialize_cache
from ..cache.tempref import temprefmanager
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro
from ..reactor import Reactor
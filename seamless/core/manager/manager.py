import weakref
import functools
import threading
import asyncio
import traceback
import sys

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
        from ..cache.tempref import temprefmanager
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

    @mainthread
    def register_transformer(self, transformer):
        self.cachemanager.register_transformer(transformer)
        self.livegraph.register_transformer(transformer)
        self.taskmanager.register_transformer(transformer)

    @mainthread
    def register_reactor(self, reactor):
        self.cachemanager.register_reactor(reactor)
        self.livegraph.register_reactor(reactor)
        self.taskmanager.register_reactor(reactor)

    @mainthread
    def register_macro(self, macro):
        self.cachemanager.register_macro(macro)
        self.livegraph.register_macro(macro)
        self.taskmanager.register_macro(macro)

    @mainthread
    def register_macropath(self, macropath):
        self.livegraph.register_macropath(macropath)
        self.taskmanager.register_macropath(macropath)

    ##########################################################################
    # API section II: Actions
    ##########################################################################

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
            reason = StatusReasonEnum.UNDEFINED
            self.cancel_cell(cell, void=True, reason=reason)
        else:
            reason = None
            old_checksum = self.get_cell_checksum(cell)
            if old_checksum is not None:
                self.cancel_cell(cell, void=False)
        self._set_cell_checksum(
            cell, checksum, 
            (checksum is None), status_reason=reason
        )

    def _set_cell_checksum(self, cell, checksum, void, status_reason=None):
        # NOTE: Any cell task depending on the old checksum must have been canceled already
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        if void:
            assert status_reason is not None
            assert checksum is None
        authority = self.livegraph.has_authority(cell)
        cachemanager = self.cachemanager
        old_checksum = cell._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, cell, authority)
        cell._checksum = checksum
        cell._void = void
        cell._status_reason = status_reason
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, cell, authority)
            if cell._mount is not None:
                buffer, checksum = self.get_cell_buffer_and_checksum(cell)
                self.mountmanager.add_cell_update(cell, checksum, buffer)

    def _set_transformer_checksum(self, transformer, checksum, void, status_reason=None):
        # NOTE: Any cell task depending on the old checksum must have been canceled already
        assert checksum is None or isinstance(checksum, bytes), checksum
        if void:
            assert status_reason is not None
        assert isinstance(void, bool), void
        cachemanager = self.cachemanager
        old_checksum = transformer._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, transformer, False)
        transformer._checksum = checksum
        transformer._void = void
        transformer._status_reason = status_reason
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, transformer, False)

    def _set_macro_exception(self, macro, exception):
        if exception is None:
            self.cachemanager.macro_exceptions[macro] = None
            return
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n"% str(macro) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)
        self.cancel_macro(macro, True, reason=StatusReasonEnum.ERROR)
        self.cachemanager.macro_exceptions[macro] = exc      

    @run_in_mainthread
    def set_cell(self, cell, value):
        assert self.livegraph.has_authority(cell)
        reason = None
        if value is None:
            reason = StatusReasonEnum.UNDEFINED
        self.cancel_cell(cell, value is None, reason)
        task = SetCellValueTask(self, cell, value)
        task.launch()

    @run_in_mainthread
    def set_cell_buffer(self, cell, buffer, checksum):
        assert self.livegraph.has_authority(cell), cell
        reason = None
        if buffer is None:
            reason = StatusReasonEnum.UNDEFINED
        self.cancel_cell(cell, buffer is None, reason)
        task = SetCellBufferTask(self, cell, buffer, checksum)
        task.launch()

    def _get_cell_checksum_and_void(self, cell):
        while 1:
            if self._destroyed or cell._destroyed:
                break
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
        if cell._destroyed:
            return None
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

    @run_in_mainthread
    def _set_reactor_exception(self, reactor, codename, exception):
        if exception is None:
            self.cachemanager.reactor_exceptions[reactor] = None
            return 
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s, code name %s:\n"% (str(reactor), codename) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)
        self.cachemanager.reactor_exceptions[reactor] = (codename, exc)
        reason = StatusReasonEnum.ERROR
        self.cancel_reactor(reactor, void=True, reason=reason)

    @mainthread
    def cancel_cell(self, cell, void, origin_task=None, reason=None):
        """Cancels all tasks depending on cell, and sets all dependencies to None. 
If void=True, all dependencies are set to void as well.
If origin_task is provided, that task is not cancelled."""
        assert isinstance(cell, Cell)
        if cell._destroyed:
            return
        if cell._canceling:
            return
        try:
            cell._canceling = True
            if (not void) and cell._void:
                return
            self.taskmanager.cancel_cell(cell, origin_task=origin_task)
            if reason is None:
                reason = StatusReasonEnum.UPSTREAM
            self._set_cell_checksum(cell, None, void, status_reason=reason)
            livegraph = self.livegraph
            accessors = livegraph.cell_to_downstream[cell]
            for accessor in accessors:            
                self.cancel_accessor(accessor, void)        
        finally:
            cell._canceling = False

    @mainthread
    def cancel_accessor(self, accessor, void, origin_task=None):
        assert isinstance(accessor, ReadAccessor)
        self.taskmanager.cancel_accessor(accessor, origin_task=origin_task)
        if accessor.expression is not None:           
            self.livegraph.decref_expression(accessor.expression, accessor)
            accessor.expression = None
            accessor._checksum = None
        target = accessor.write_accessor.target()
        reason = StatusReasonEnum.UPSTREAM
        if isinstance(target, Cell):
            return self.cancel_cell(target, void=void)
        elif isinstance(target, Worker):
            if isinstance(target, Transformer):
                return self.cancel_transformer(target, void=void, reason=reason)
            elif isinstance(target, Reactor):
                return self.cancel_reactor(target, void=void, reason=reason)

    @mainthread
    def cancel_transformer(self, transformer, void, reason=None):
        assert isinstance(transformer, Transformer)
        self.taskmanager.cancel_transformer(transformer)
        if (not void) and transformer._void:
            return
        if void:
            assert reason is not None        
        self._set_transformer_checksum(transformer, None, void, status_reason=reason)
        livegraph = self.livegraph
        accessors = livegraph.transformer_to_downstream[transformer]
        for accessor in accessors:            
            self.cancel_accessor(accessor, void)        

    @mainthread
    def cancel_reactor(self, reactor, void, reason=None):
        assert isinstance(reactor, Reactor)
        if (not void) and reactor._void:
            return
        if reason is None:
            reason = StatusReasonEnum.UPSTREAM
        livegraph = self.livegraph
        reactor._pending = (not void)
        reactor._void = void
        reactor._status_reason = reason 
        outputpins = [pinname for pinname in reactor._pins \
            if reactor._pins[pinname].io == "output" ]
        if void:
            for pinname in outputpins:
                accessors = livegraph.reactor_to_downstream[reactor][pinname]
                for accessor in accessors:            
                    self.cancel_accessor(accessor, True)        

    @mainthread
    def cancel_macro(self, macro, void, reason=None):
        assert isinstance(macro, Macro)
        macro._last_inputs = None 
        """
        Macros are NOT fully deterministic on their inputs!
        This is because of libcell, and libraries may change
        Therefore, when a library is re-registered, it invokes
         cancel_macro + macro update, and resetting _last_inputs
         makes sure it gets re-executed
        """
        gen_context = macro._gen_context
        if gen_context is not None:
            gen_context.destroy()
        if void:
            macro._void = True
            macro._status_reason = reason

    ##########################################################################
    # API section ???: Connection support
    ##########################################################################

    @mainthread
    def connect(self, source, source_subpath, target, target_subpath):
        if isinstance(target, Cell):
            self.livegraph._will_lose_authority.add(target)
        task = UponConnectionTask(
            self, source, source_subpath, target, target_subpath
        )
        task.launch()


    def cell_from_pin(self, pin):
        return self.livegraph.cell_from_pin(pin)


    def _verify_connect(self, current_macro, source, target):        
        from ..macro import Path
        assert source._get_manager() is self, source._get_manager()
        assert source._root() is target._root()
        source_macro = source._get_macro()
        target_macro = target._get_macro()
        if source_macro is not None or target_macro is not None:
            if current_macro is not None:
                if not source_macro._context()._part_of2(current_macro._context()):
                    msg = "%s is not part of current %s"
                    raise Exception(msg % (source_macro, current_macro))
                if not target_macro._context()._part_of2(current_macro._context()):
                    msg = "%s is not part of current %s"
                    raise Exception(msg % (target_macro, current_macro))
        path_source = (source_macro is not current_macro or isinstance(source, Path))
        path_target = (target_macro is not current_macro or isinstance(target, Path))
        if path_source and path_target:
            msg = "Neither %s (governing %s) nor %s (governing %s) was created by current macro %s"
            raise Exception(msg % (source_macro, source, target_macro, target, current_macro))
        return path_source, path_target

    ##########################################################################
    # API section ???: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        self.cachemanager.destroy_cell(cell)
        self.livegraph.destroy_cell(self, cell)
        self.taskmanager.destroy_cell(cell, full=True)

    def _destroy_transformer(self, transformer):
        self.cachemanager.destroy_transformer(transformer)
        self.livegraph.destroy_transformer(self, transformer)
        self.taskmanager.destroy_transformer(transformer, full=True)

    def _destroy_reactor(self, reactor):
        self.cachemanager.destroy_reactor(reactor)
        self.livegraph.destroy_reactor(self, reactor)
        self.taskmanager.destroy_reactor(reactor, full=True)

    def _destroy_macro(self, macro):
        self.cachemanager.destroy_macro(macro)
        self.livegraph.destroy_macro(self, macro)
        self.taskmanager.destroy_macro(macro, full=True)
        if len(macro._paths):
            for path in macro._paths.values():
                path.destroy()

    def _destroy_macropath(self, macropath):
        self.livegraph.destroy_macropath(macropath)
        self.taskmanager.destroy_macropath(macropath)

    @mainthread
    def destroy(self, from_del=False):
        from ..macro import _global_paths
        if self._destroyed:
            return
        self._destroyed = True
        ctx = self.ctx()
        if ctx is None:
            return
        ctx.destroy()
        self.mountmanager.unmount_context(ctx, from_del=from_del, toplevel=True)
        for path in list(self.livegraph.macropath_to_upstream.keys()):
            path.destroy()
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
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro
from ..reactor import Reactor
from .accessor import ReadAccessor
from ..status import StatusReasonEnum
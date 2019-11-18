import weakref
import functools
import threading
import asyncio
import traceback
import sys
import copy

def mainthread(func):
    def func2(*args, **kwargs):
        if threading.current_thread is None: # destruction at exit
            return
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
    def __init__(self):
        from .livegraph import LiveGraph
        from .cachemanager import CacheManager
        from .taskmanager import TaskManager        
        self.contexts = weakref.WeakSet()
        self.last_ctx = lambda: None
        from ... import communion_server
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

        # for now, just a single global sharemanager
        from ..share import sharemanager
        self.sharemanager = sharemanager
        sharemanager.start()

        from ...communion_server import communion_server
        communion_server.start()

    def add_context(self, ctx):
        assert ctx._toplevel
        self.contexts.add(ctx)
        self.last_ctx = weakref.ref(ctx)

    def remove_context(self, ctx):
        assert ctx._toplevel
        self.contexts.discard(ctx)

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
        self.cachemanager.register_structured_cell(structured_cell)
        self.taskmanager.register_structured_cell(structured_cell)
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
    def set_cell_checksum(self, cell, checksum, initial, from_structured_cell):
        """Setting a cell checksum.
  (This is done from the command line, usually at graph loading)
  initial=True in case of graph loading; from_structured_cell=True when triggered from StructuredCell)
  If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph)
  If "initial" is true, but "from_structured_cell" is not, the cell:
  - Must be a simple cell
  - or: must be the auth cell of a structured cell.
    In that case, the checksum is temporary, and converted to a value that is set on the auth handle of the structured cell
  If neither "initial" nor "from_structured_cell" is true, the cell:
  - cannot be the .data or .buffer attribute of a StructuredCell
  - cannot have any incoming connection.
  - cannot be a deep cell (having a hash pattern)

  If the new checksum is None, do a cell void cancellation.  
  Else: 
    If old checksum is not None, do a cell cancellation.
    Set the cell as being non-void, set the checksum (direct attribute access), and launch a cell update task. 

        """
        sc_data = self.livegraph.datacells.get(cell) 
        sc_buf = self.livegraph.buffercells.get(cell)
        sc_schema = self.livegraph.schemacells.get(cell, [])
        if not initial:            
            if from_structured_cell:
                if sc_data is None and sc_buf is None and not len(sc_schema):
                    assert cell._structured_cell is not None
                    assert cell._structured_cell.auth is cell, cell
            else:
                assert cell._structured_cell is None
                assert cell._hash_pattern is None
                assert sc_data is None and sc_buf is None
                assert self.livegraph.has_authority(cell)
                assert sc_buf is None
        else:  # initial
            if not from_structured_cell and cell._structured_cell is not None:
                assert cell._structured_cell.auth is cell, cell
                if checksum is None:
                    value = None
                else:
                    buffer = GetBufferTask(self, checksum).launch_and_await()
                    value = DeserializeBufferTask(
                        self, buffer, checksum, "mixed", False
                    ).launch_and_await()
                return cell._structured_cell.set_no_inference(value)
        if checksum is None:
            reason = StatusReasonEnum.UNDEFINED
            if not from_structured_cell:
                self.cancel_cell(cell, void=True, reason=reason)
        else:
            reason = None
            old_checksum = self.get_cell_checksum(cell)
            if old_checksum is not None:
                if not from_structured_cell:
                    self.cancel_cell(cell, void=False)
        #and cell._context()._macro is None: # TODO: forbid
        self._set_cell_checksum(
            cell, checksum, 
            (checksum is None), status_reason=reason
        )
        if not from_structured_cell: # also for initial...
            CellUpdateTask(self, cell).launch()
        if sc_schema:
            value = cell.data
            self.update_schemacell(cell, value, None)

    def _set_cell_checksum(self, cell, checksum, void, status_reason=None, prelim=False):
        # NOTE: Any cell task depending on the old checksum must have been canceled already
        if cell._destroyed:
            return
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        if void:
            assert status_reason is not None
            assert checksum is None
        if cell._structured_cell:
            authority = True
        else:
            authority = self.livegraph.has_authority(cell)
        cachemanager = self.cachemanager
        old_checksum = cell._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, cell, authority)
        cell._checksum = checksum
        cell._void = void
        cell._status_reason = status_reason
        cell._prelim = prelim
        if checksum != old_checksum:
            observer = cell._observer
            if observer is not None:
                cs = checksum.hex() if checksum is not None else None
                observer(cs)
            cachemanager.incref_checksum(checksum, cell, authority)            
            if cell._mount is not None:
                buffer = self.cachemanager.buffer_cache.get_buffer(checksum)
                self.mountmanager.add_cell_update(cell, checksum, buffer)
            if cell._share is not None:
                self.sharemanager.add_cell_update(cell, checksum)

    def _set_inchannel_checksum(self, inchannel, checksum, void, status_reason=None, prelim=False):
        ###print("INCH", inchannel.subpath, checksum is not None)
        ###import traceback; traceback.print_stack(limit=5)
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        if void:
            assert status_reason is not None
            assert checksum is None
        cachemanager = self.cachemanager
        old_checksum = inchannel._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, inchannel, False)
        inchannel._checksum = checksum
        inchannel._void = void
        inchannel._status_reason = status_reason
        inchannel._prelim = prelim        
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, inchannel, False)
            sc = inchannel.structured_cell()
            sc.modified_inchannels.add(inchannel)
            self.structured_cell_join(sc)

    def _set_transformer_checksum(self,
        transformer, checksum, void, *,
        prelim, status_reason=None
    ):
        # NOTE: Any cell task depending on the old checksum must have been canceled already
        assert checksum is None or isinstance(checksum, bytes), checksum
        if void:
            assert status_reason is not None
            assert checksum is None
            assert prelim == False
        assert isinstance(void, bool), void
        cachemanager = self.cachemanager
        old_checksum = transformer._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, transformer, False)
        transformer._prelim_result = prelim
        transformer._checksum = checksum
        transformer._void = void
        transformer._status_reason = status_reason
        if not prelim:
            transformer._progress = 0.0
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, transformer, False)

    def _set_transformer_progress(self, transformer, progress):
        transformer._progress = progress

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
    def set_auth_path(self, structured_cell, path, value):
        self.cancel_scell_inpath(
            structured_cell, path, value is None,
            from_auth=True
        )
        self.taskmanager.cancel_structured_cell(structured_cell)
    

    def update_schemacell(self, schemacell, value, structured_cell):
        livegraph = self.livegraph
        structured_cells = livegraph.schemacells[schemacell]
        for sc in structured_cells:            
            if sc is structured_cell:
                continue           
            self.taskmanager.cancel_structured_cell(sc)
            sc._schema_value = copy.deepcopy(value)
            self.structured_cell_join(sc)

    def structured_cell_join(self, structured_cell):
        # First cancel all ongoing joins
        self.taskmanager.cancel_structured_cell(structured_cell)
        task = StructuredCellJoinTask(
            self, structured_cell
        )
        task.launch()

    @run_in_mainthread
    def set_cell_buffer(self, cell, buffer, checksum):
        assert cell._hash_pattern is None
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
            assert isinstance(buffer, bytes)
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
        if cell._structured_cell is not None:
            assert cell._structured_cell.schema is cell, cell # cancel_cell only on schema cells, else use cancel_scell_inpath
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
    def cancel_scell_inpath(self, sc, path, void, from_auth=False):
        from .tasks.structured_cell import overlap_path
        assert isinstance(sc, StructuredCell)
        cell = sc._data
        if not from_auth and path in sc.inchannels:        
            if void:
                reason = StatusReasonEnum.UPSTREAM
            else:
                reason = None
            ic = sc.inchannels[path]
            self._set_inchannel_checksum(
                ic, None, void,
                status_reason=reason
            )
        for outchannel in sc.outchannels:
            if overlap_path(outchannel, path):
                self.cancel_cell_path(cell, outchannel, void)
        self._set_cell_checksum(cell, None, void, StatusReasonEnum.UPSTREAM)
        self._set_cell_checksum(sc.buffer, None, void, StatusReasonEnum.UPSTREAM)

    @mainthread
    def cancel_cell_path(self, cell, path, void):
        assert isinstance(cell, Cell)
        assert cell._structured_cell is not None
        assert cell._structured_cell._data is cell, (cell, cell._structured_cell._data)
        if cell._destroyed:
            return
        livegraph = self.livegraph
        all_accessors = livegraph.paths_to_downstream[cell]
        for accessor in all_accessors[path]:
            self.cancel_accessor(accessor, void)        

    @mainthread
    def cancel_accessor(self, accessor, void, origin_task=None):
        assert isinstance(accessor, ReadAccessor)
        self.taskmanager.cancel_accessor(accessor, origin_task=origin_task)
        if accessor.expression is not None:           
            self.livegraph.decref_expression(accessor.expression, accessor)
            accessor.expression = None
            accessor._checksum = None
        accessor._void = void
        target = accessor.write_accessor.target()
        reason = StatusReasonEnum.UPSTREAM
        if isinstance(target, Cell):
            if accessor.write_accessor.path is None:
                if target._structured_cell is not None:
                    assert target._structured_cell.schema is target, target # cancel_cell only on schema cells, else use cancel_scell_inpath
                return self.cancel_cell(target, void=void)
            else:
                assert target._structured_cell is not None
                self.cancel_scell_inpath(
                    target._structured_cell, 
                    accessor.write_accessor.path,
                    void=void
                )
        elif isinstance(target, Worker):
            if isinstance(target, Transformer):
                return self.cancel_transformer(target, void=void, reason=reason)
            elif isinstance(target, Reactor):
                return self.cancel_reactor(target, void=void, reason=reason)
            elif isinstance(target, Macro):
                return self.cancel_macro(target, void=void, reason=reason)
            else:
                raise TypeError(target)
    @mainthread
    def cancel_transformer(self, transformer, void, reason=None):
        assert isinstance(transformer, Transformer)
        self.taskmanager.cancel_transformer(transformer)
        if (not void) and transformer._void:
            return
        if void:
            assert reason is not None
            if transformer._void:
                curr_reason = transformer._status_reason
                if curr_reason.value < reason.value:
                    return
        self._set_transformer_checksum(
            transformer, None, void, 
            status_reason=reason,
            prelim = False
        )
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
        if void and reactor._void:
            curr_reason = reactor._status_reason
            if curr_reason.value < reason.value:
                return
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
            macro._gen_context = None
        if void:
            if macro._void:
                curr_reason = macro._status_reason
                if curr_reason.value < reason.value:
                    return
            macro._void = True
            macro._status_reason = reason

    ##########################################################################
    # API section ???: Connection support
    ##########################################################################

    @mainthread
    def connect(self, source, source_subpath, target, target_subpath):
        from ..link import Link
        if isinstance(source, Link):
            source = source.get_linked()
        if isinstance(target, Link):
            target = target.get_linked()            
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
        paths = cell._paths
        if paths is not None:
            for macropath in list(paths):
                macropath._unbind()
        self.cachemanager.destroy_cell(cell)
        self.livegraph.destroy_cell(self, cell)
        self.taskmanager.destroy_cell(cell, full=True)

    def _destroy_structured_cell(self, structured_cell):
        # no need to notify livegraph; cell destruction does the job already
        self.cachemanager.destroy_structured_cell(structured_cell)
        self.taskmanager.destroy_structured_cell(structured_cell)        

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
        if self._destroyed:
            return
        self._destroyed = True
        contexts = list(self.contexts)        
        self.contexts.clear()
        for ctx in contexts:
            ctx.destroy(from_del=from_del)
        self.last_ctx = None        
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
    DeserializeBufferTask, UponConnectionTask, CellUpdateTask
)

from ..protocol.calculate_checksum import checksum_cache
from ..protocol.deserialize import deserialize_cache
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro, _global_paths
from ..reactor import Reactor
from .accessor import ReadAccessor
from ..status import StatusReasonEnum
from ..structured_cell import StructuredCell
from .tasks.structured_cell import StructuredCellJoinTask
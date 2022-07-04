import weakref
import functools
import threading
import asyncio
import traceback
import sys
from copy import deepcopy

from seamless.core.cache import CacheMissError

from ..status import StatusReasonEnum

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

def mainthread(func):
    def func2(*args, **kwargs):
        if threading.current_thread is None: # destruction at exit
            return
        assert threading.current_thread() == threading.main_thread()
        return func(*args, **kwargs)
    functools.update_wrapper(func2, func)
    return func2

def with_cancel_cycle(func):
    def func2(*args, **kwargs):
        if threading.current_thread is None: # destruction at exit
            return
        assert threading.current_thread() == threading.main_thread()
        manager = args[0]
        if manager._destroyed:
            return
        taskmanager = manager.taskmanager
        if not manager.cancel_cycle.cleared:
            print("ERROR: manager cancel cycle was not cleared")
        try:
            taskmanager.run_all_synctasks()
            manager.cancel_cycle.cleared = False
            result = func(*args, **kwargs)
            manager.cancel_cycle.resolve()
        finally:
            manager.cancel_cycle._clear()
            taskmanager.run_all_synctasks()
        return result
    functools.update_wrapper(func2, func)
    return func2

def _run_in_mainthread(func):
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
    _highlevel_refs = 0
    _last_ctx = None
    def __init__(self):
        self._destroyed = True
        from seamless import check_original_event_loop
        check_original_event_loop()
        global is_dummy_mount
        from .livegraph import LiveGraph
        from .cachemanager import CacheManager
        from .taskmanager import TaskManager
        from .cancel import CancellationCycle
        self.contexts = weakref.WeakSet()
        self.livegraph = LiveGraph(self)
        self.cachemanager = CacheManager(self)
        self.taskmanager = TaskManager(self)
        self.cancel_cycle = CancellationCycle(self)
        self._destroyed = False
        loop_run_synctasks = self.taskmanager.loop_run_synctasks()
        asyncio.ensure_future(loop_run_synctasks)

        # for now, just a single global temprefmanager
        from ..cache.tempref import temprefmanager
        self.temprefmanager = temprefmanager

        # for now, just a single global mountmanager
        from ..mount import mountmanager, is_dummy_mount
        self.mountmanager = mountmanager
        mountmanager.start()

        # for now, just a single global sharemanager
        from ..share import sharemanager, shareserver
        self.sharemanager = sharemanager
        self.shareserver = shareserver
        sharemanager.start()


    def add_context(self, ctx):
        assert ctx._toplevel
        self.contexts.add(ctx)
        self._last_ctx = weakref.ref(ctx)
    
    def last_ctx(self):
        result = None
        if self._last_ctx is not None:
            result = self._last_ctx()
        if result is not None:
            return result
        if not len(self.contexts):
            return None
        for ctx in self.contexts:
            self._last_ctx = weakref.ref(ctx)
            return ctx

    def remove_context(self, ctx):
        assert ctx._toplevel
        self.contexts.discard(ctx)
        if not len(self.contexts) and self._highlevel_refs < 1:
            self.destroy()

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

    def _upon_set_cell_checksum(self, cell, checksum, void, trigger_bilinks):
        livegraph = self.livegraph
        if checksum is not None:
            for traitlet in cell._traitlets:
                # TODO: block the async mainloop during the receive_update call
                try:
                    traitlet.receive_update(checksum)
                except Exception:
                    traceback.print_exc()
        if not is_dummy_mount(cell._mount):
            try:
                buffer = get_buffer(checksum, remote=True)  # not async, so OK
                self.mountmanager.add_cell_update(cell, checksum, buffer)
            except Exception:
                traceback.print_exc()            
        if cell._share is not None:
            try:
                self.sharemanager.add_cell_update(cell, checksum)
            except Exception:
                traceback.print_exc()
        if checksum is not None and trigger_bilinks:
            try:
                self.livegraph.activate_bilink(cell, checksum)
            except Exception:
                traceback.print_exc()
        if (void or checksum is not None) and not len(livegraph._destroying):
            if cell in livegraph.cell_from_macro_elision:
                elision = livegraph.cell_from_macro_elision[cell]
                if elision.macro.ctx is not None and not elision.macro.ctx._destroyed:
                    #print("UP!", cell, void, checksum.hex() if checksum is not None else None)
                    elision.update()


    @_run_in_mainthread
    def set_cell_checksum(self,
        cell, checksum, *,
        initial, from_structured_cell, trigger_bilinks
    ):
        """Setting a cell checksum.
  (This is done from the command line, usually at graph loading)
  initial=True in case of graph loading; from_structured_cell=True when triggered from StructuredCell)

  NOTE: Seamless tasks must not call this function, unless they check afterwards that they were not cancelled because of it.

  If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph)
  If "from_structured_cell" is True, the function is triggered by StructuredCell state maintenance routines
  This function takes care of the incref/decref of checksums inside a deep structure

  If "initial" is true, but "from_structured_cell" is not, the cell must be a simple cell

  If neither "initial" nor "from_structured_cell" is true, the cell:
  - cannot be the .data or .buffer attribute of a StructuredCell
  - cannot have any incoming connection.
  - cannot be a deep cell (having a hash pattern)

  If the new checksum is None, do a cell void cancellation.
  Else:
    If old checksum is not None, do a cell cancellation.
    Set the cell as being non-void, set the checksum (direct attribute access), and launch a cell update task.
        """
        if self._destroyed or cell._destroyed:
            return
        sc_data = self.livegraph.datacells.get(cell)
        sc_buf = self.livegraph.buffercells.get(cell)
        sc_schema = self.livegraph.schemacells.get(cell, [])
        if not initial:
            self.taskmanager.run_all_synctasks()
            if from_structured_cell:
                if sc_data is None and sc_buf is None and not len(sc_schema):
                    assert cell._structured_cell is not None
            else:
                assert cell._structured_cell is None
                assert sc_data is None and sc_buf is None
                if sc_schema is None:
                    assert cell.has_independence()
                assert sc_buf is None
        else:  # initial
            assert not trigger_bilinks
            if not from_structured_cell and cell._structured_cell is not None:
                assert cell._structured_cell.auth is cell, cell
        if checksum is None:
            assert not initial
            reason = StatusReasonEnum.UNDEFINED
            if not from_structured_cell:
                if cell._structured_cell is None or sc_schema:
                    self.cancel_cell(cell, void=True, reason=reason)
        else:
            reason = None
            old_checksum = cell._checksum # avoid infinite task loop...
        #and cell._context()._macro is None: # TODO: forbid
        if not initial and not from_structured_cell:
            self.cancel_cell(cell, (checksum is None))
        else:
            if cell._structured_cell is None:
                unvoid_cell(cell, self.livegraph)
        self._set_cell_checksum(
            cell, checksum,
            (checksum is None), status_reason=reason,
            trigger_bilinks=trigger_bilinks
        )
        updated = False
        if not from_structured_cell: # also for initial...
            if cell._structured_cell is not None and cell._structured_cell.auth is cell:
                scell = cell._structured_cell
                scell._modified_auth = True
                if get_scell_state(scell) == "void" and scell.auth is not scell._data:
                    self._set_cell_checksum(scell._data, None, void=True, status_reason=reason)
                self.structured_cell_trigger(scell)
            else:
                if checksum is not None:
                    unvoid_cell(cell, self.livegraph)
                    if cell._structured_cell is None or sc_schema:
                        CellUpdateTask(self, cell).launch()
                        updated = True
        if sc_schema:
            if from_structured_cell and not updated:
                CellUpdateTask(self, cell).launch()
                updated = True
            def update_schema():
                value = self.resolve(checksum, "plain")
                self.update_schemacell(cell, value)
            self.taskmanager.add_synctask(update_schema, (), {}, False)

        if initial:
            self.trigger_all_fallbacks(cell)

    def _set_cell_checksum(self,
        cell, checksum, void, status_reason=None, prelim=False, trigger_bilinks=True
    ):
        """
        NOTE: Any cell task depending on the old checksum must have been canceled already
        NOTE: This function must take place within one async step
        Therefore, the direct or indirect call of _sync versions of coroutines
        (e.g. deserialize_sync, which launches coroutines and waits for them)
        IS NOT ALLOWED

        On the other hand, since cachemanager.incref_checksum is called,
         deep structures have their contained checksums automatically incref'ed, 
         and decref'ed for the old value
        NOTE: this function blindly assumes that the checksum is parseable
         for the cell's celltype, and in fact triggers a guarantee.
        If you are paranoid about this, do not call this function unless you
         have verified the parsability yourself.
        """
        if cell._destroyed:
            return
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void

        if void:
            assert status_reason is not None
            assert checksum is None
        else:
            status_reason = None

        livegraph = self.livegraph
        if len(livegraph.schemacells[cell]):
            independent = True
            value = None
            if checksum is not None:
                buf = self._get_buffer(checksum,deep=False)
                value = deserialize_sync(buf, checksum, "plain", copy=False)
            for sc in livegraph.schemacells[cell]:
                sc._schema_value = deepcopy(value)
        elif cell._structured_cell is not None:
            independent = (cell._structured_cell.auth is cell)
        else:
            independent = cell.has_independence()
        cachemanager = self.cachemanager
        old_checksum = cell._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, cell, independent, False)
        
        print_debug("SET CHECKSUM", cell, "None:", checksum is None, checksum == old_checksum)
        if checksum is not None:
            buffer_cache.guarantee_buffer_info(checksum, cell.celltype)
        cell._checksum = checksum
        cell._void = void
        cell._status_reason = status_reason
        cell._prelim = prelim
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, cell, independent, False)
            observer = cell._observer
            if (observer is not None or livegraph._hold_observations) and ((checksum is not None) or void):
                cs = checksum.hex() if checksum is not None else None
                if not livegraph._hold_observations and not len(livegraph._destroying):
                    try:
                        cell._observer(cs)
                    except Exception:
                        traceback.print_exc()
                else:
                    livegraph._observing.append((cell, cs))
            self._upon_set_cell_checksum(cell, checksum, void, trigger_bilinks)

    def _set_inchannel_checksum(self, inchannel, checksum, void, status_reason=None, *,
      prelim=False, from_cancel_system=False
    ):
        ###import traceback; traceback.print_stack(limit=5)
        assert checksum is None or isinstance(checksum, bytes), checksum
        assert isinstance(void, bool), void
        if void:
            assert status_reason is not None
            assert checksum is None
            assert not prelim
        sc = inchannel.structured_cell()
        if sc._destroyed:
            return

        cachemanager = self.cachemanager
        if not sc._cyclic:
            assert not (inchannel._void and (inchannel._checksum is not None))
        old_checksum = inchannel._checksum
        if old_checksum is not None and old_checksum != checksum:
            cachemanager.decref_checksum(old_checksum, inchannel, False, False)
        inchannel._checksum = checksum
        inchannel._void = void
        inchannel._status_reason = status_reason
        inchannel._prelim = prelim
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, inchannel, False, False)
            if not from_cancel_system:
                self.structured_cell_trigger(sc)

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
            cachemanager.decref_checksum(old_checksum, transformer, False, True)
        transformer._prelim_result = prelim
        transformer._checksum = checksum
        transformer._void = void
        transformer._status_reason = status_reason
        if not prelim:
            transformer._progress = 0.0
        if checksum != old_checksum:
            cachemanager.incref_checksum(checksum, transformer, False, True)

    def _set_transformer_progress(self, transformer, progress):
        transformer._progress = progress

    def _set_macro_exception(self, macro, exception):
        if exception is None:
            self.cachemanager.macro_exceptions[macro] = None
            return
        exc = traceback.format_exception(
            type(exception),
            exception,
            exception.__traceback__,
            chain=False
        )
        exc = exc[4:]
        exc = "".join(exc)
        """
        msg = "Exception in %s:\n"% str(macro) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)
        """
        self.cancel_macro(macro, True, reason=StatusReasonEnum.ERROR)
        self.cachemanager.macro_exceptions[macro] = exc

    @_run_in_mainthread
    def set_cell(self, cell, value, origin_reactor=None):
        if self._destroyed or cell._destroyed:
            return
        assert cell.has_independence(), "{} is not independent".format(cell)
        assert cell._structured_cell is None, cell
        reason = None
        if value is None:
            reason = StatusReasonEnum.UNDEFINED
        self.taskmanager.run_all_synctasks()
        if value is not None and cell._void:
            unvoid_cell(cell, self.livegraph)
        else:
            self.cancel_cell(cell, value is None, reason)
        task = SetCellValueTask(self, cell, value, origin_reactor=origin_reactor)
        task.launch()

    def update_schemacell(self, schemacell, value):
        livegraph = self.livegraph
        structured_cells = livegraph.schemacells[schemacell]
        for sc in structured_cells:
            sc._schema_value = deepcopy(value)
            self.structured_cell_trigger(sc, update_schema=True)

    @_run_in_mainthread
    def set_cell_buffer(self, cell, buffer, checksum):
        if self._destroyed or cell._destroyed:
            return
        assert cell._hash_pattern is None
        assert cell.has_independence(), "{} is not independent".format(cell)
        assert cell._structured_cell is None, cell
        reason = None
        if buffer is None:
            reason = StatusReasonEnum.UNDEFINED
        self.taskmanager.run_all_synctasks()
        if buffer is not None and cell._void:
            unvoid_cell(cell, self.livegraph)
        else:
            self.cancel_cell(cell, buffer is None, reason)
        task = SetCellBufferTask(self, cell, buffer, checksum)
        task.launch()

    def _get_cell_checksum_and_void(self, cell):
        fallback = self.get_fallback(cell)
        if fallback is not None:
            return fallback._checksum, fallback._void
        else:
            return cell._checksum, cell._void

    @mainthread
    def get_cell_checksum(self, cell):
        checksum, _ = self._get_cell_checksum_and_void(cell)
        return checksum

    @mainthread
    def get_cell_void(self, cell):
        _, void = self._get_cell_checksum_and_void(cell)
        return void

    def _get_buffer(self, checksum, deep):
        if asyncio.get_event_loop().is_running():
            buffer = get_buffer(checksum, remote=True, deep=deep)
            if buffer is None:
                raise CacheMissError(checksum.hex())
            return buffer
        if checksum is None:
            return None
        empty_dict_checksum = 'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c'
        if checksum.hex() == empty_dict_checksum:
            return b"{}\n"
        buffer = checksum_cache.get(checksum)
        if buffer is not None:
            assert isinstance(buffer, bytes)
            return buffer
        try:
            return GetBufferTask(self, checksum).launch_and_await()
        except asyncio.CancelledError:
            return None

    @mainthread
    def get_cell_buffer_and_checksum(self, cell):
        checksum = self.get_cell_checksum(cell)
        deep = cell._hash_pattern is not None
        buffer = self._get_buffer(checksum,deep)
        return buffer, checksum

    @mainthread
    def get_cell_value(self, cell, copy):
        if cell._destroyed:
            return None
        checksum = self.get_cell_checksum(cell)
        if checksum is None:
            return None
        celltype = cell._celltype
        if not copy:
            cached_value = deserialize_cache.get((checksum, celltype))
            if cached_value is not None:
                return deepcopy(cached_value)
        return self.resolve(checksum, celltype, copy=copy)

    def resolve(self, checksum, celltype=None, copy=True):
        """Returns the data buffer that corresponds to the checksum.
        If celltype is provided, a value is returned instead

        The checksum must be a SHA3-256 hash, as hex string or as bytes"""
        if checksum is None:
            return None
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        # set deep to True, since we do want to check the fairserver
        buffer = self._get_buffer(checksum,deep=True)
        if celltype is None:
            return buffer
        if asyncio.get_event_loop().is_running():
            return deserialize_sync(buffer, checksum, celltype, copy=copy)
        task = DeserializeBufferTask(
            self, buffer, checksum, celltype,
            copy=copy
        )
        try:
            value = task.launch_and_await()
        except asyncio.CancelledError:
            return None
        return value

    def set_elision(self, macro, input_cells, output_cells):
        from ..cache.elision import Elision
        Elision(self.livegraph, macro, input_cells, output_cells)

    ##########################################################################
    # API section III: Cancellation
    ##########################################################################

    @_run_in_mainthread
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

    @with_cancel_cycle
    def cancel_cell(self, cell, void, origin_task=None, reason=None):
        """Cancels all tasks depending on cell, and sets all dependencies to None.
If void=True, all dependencies are set to void as well.
If origin_task is provided, that task is not cancelled."""
        assert isinstance(cell, Cell)
        if cell._structured_cell is not None:
            assert cell._structured_cell.schema is cell, cell # cancel_cell only on schema cells, else use cancel_scell_inpath
        if cell._destroyed:
            return

        if origin_task is not None:
            self.cancel_cycle.origin_task = origin_task
        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM
        self.cancel_cycle.cancel_cell(cell, void=void, reason=reason)

    @with_cancel_cycle
    def cancel_scell_inpath(self, sc, path, void, reason=None):
        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM
        self.cancel_cycle.cancel_scell_inpath(sc, path, void=void, reason=reason)

    @with_cancel_cycle
    def structured_cell_trigger(self, scell, *, update_schema=False, void=False):
        self.cancel_cycle.trigger_scell(scell, update_schema=update_schema, void=void)


    @with_cancel_cycle
    def cancel_accessor(self,
        accessor, void,
        reason=None,
        origin_task=None,
    ):
        assert isinstance(accessor, ReadAccessor)

        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM

        if origin_task is not None:
            self.cancel_cycle.origin_task = origin_task
        self.cancel_cycle.cancel_accessor(accessor, void=void, reason=reason)


    @with_cancel_cycle
    def cancel_accessors(self,
        accessors, void,
        reason=None,
        origin_task=None,
    ):
        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM

        if origin_task is not None:
            self.cancel_cycle.origin_task = origin_task

        for accessor in accessors:
            assert isinstance(accessor, ReadAccessor)

            self.cancel_cycle.cancel_accessor(accessor, void=void, reason=reason)

    @with_cancel_cycle
    def cancel_transformer(self, transformer, void, reason=None):
        assert isinstance(transformer, Transformer)
        if void and reason is None:
            reason = None
        self.cancel_cycle.cancel_transformer(transformer, void=void, reason=reason)


    @with_cancel_cycle
    def cancel_reactor(self, reactor, void, reason=None):
        assert isinstance(reactor, Reactor)
        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM
        self.cancel_cycle.cancel_reactor(reactor, void=void, reason=reason)

    @with_cancel_cycle
    def cancel_macro(self, macro, void, reason=None):
        assert isinstance(macro, Macro)
        if void and reason is None:
            reason = StatusReasonEnum.UPSTREAM
        self.cancel_cycle.cancel_macro(macro, void=void, reason=reason)

    @with_cancel_cycle
    def force_join(self,cyclic_scells):
        return self.cancel_cycle.force_join(cyclic_scells)

    ##########################################################################
    # API section IV: Connection support
    ##########################################################################

    @mainthread
    def connect(self, source, source_subpath, target, target_subpath):
        from ..unilink import UniLink
        if isinstance(source, UniLink):
            source = source.get_linked()
        if isinstance(target, UniLink):
            target = target.get_linked()
        task = UponConnectionTask(
            self, source, source_subpath, target, target_subpath
        )
        task.launch()

    @mainthread
    def bilink(self, source, target):
        from ..unilink import UniLink
        if isinstance(source, UniLink):
            source = source.get_linked()
        if isinstance(target, UniLink):
            target = target.get_linked()
        task = UponBiLinkTask(
            self, source, target
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

    def get_fallback(self, cell):
        if isinstance(cell, StructuredCell):
            cell = cell._data
        return self.livegraph.cell_to_fallback[cell]

    def set_fallback(self, cell, fallback_cell):
        #print("manager.set_fallback", cell, fallback_cell)
        if isinstance(cell, StructuredCell):
            cell = cell._data
        if len(self.livegraph.cell_to_reverse_fallbacks[cell]):
            msg = "Can't set fallback for cell {}, it is already a fallback for other cells"
            raise ValueError(msg.format(cell))
        if isinstance(fallback_cell, StructuredCell):
            fallback_cell = fallback_cell._data
        other_livegraph = fallback_cell._get_manager().livegraph
        if other_livegraph.cell_to_fallback[fallback_cell]:
            msg = "Cell {} can't be a fallback, it has already another cell as fallback"
            raise ValueError(msg.format(fallback_cell))
        if cell._destroyed:
            return
        self.livegraph.cell_to_fallback[cell] = fallback_cell

    def add_reverse_fallback(self, fallback_cell, cell):
        # Just for bookkeeping; assumes that the cell's manager has received a .set_fallback already
        if isinstance(cell, StructuredCell):
            cell = cell._data
        if isinstance(fallback_cell, StructuredCell):
            fallback_cell = fallback_cell._data
        self.livegraph.cell_to_reverse_fallbacks[fallback_cell].add(cell)

    def remove_reverse_fallback(self, fallback_cell, cell):
        # Just for bookkeeping; assumes that the cell's manager has received a .set_fallback already
        if isinstance(cell, StructuredCell):
            cell = cell._data
        if isinstance(fallback_cell, StructuredCell):
            fallback_cell = fallback_cell._data
        if fallback_cell._destroyed:
            return
        self.livegraph.cell_to_reverse_fallbacks[fallback_cell].discard(cell)

    def clear_fallback(self, cell):
        from .tasks.structured_cell import update_structured_cell
        if cell._destroyed:
            return
        if isinstance(cell, StructuredCell):
            sc = cell
            cell = sc._data
        else:
            sc = self.livegraph.datacells.get(cell)
        self.livegraph.cell_to_fallback[cell] = None
        if sc is not None:
            self.structured_cell_trigger(sc)
            update_structured_cell(sc, cell.checksum, from_fallback=False)
        else:
            CellUpdateTask(self, cell).launch()
        self._upon_set_cell_checksum(cell, cell.checksum, cell.void, True)

    def trigger_fallback(self, checksum, reverse_fallback):
        from .tasks.structured_cell import update_structured_cell
        other_manager = reverse_fallback._get_manager()
        other_livegraph = other_manager.livegraph
        if isinstance(reverse_fallback, StructuredCell):
            sc = reverse_fallback
            reverse_fallback = sc._data
        else:
            sc = other_livegraph.datacells.get(reverse_fallback)
        if sc is not None:
            other_manager.structured_cell_trigger(sc)
            update_structured_cell(sc, checksum, from_fallback=True)
        else:
            CellUpdateTask(other_manager, reverse_fallback).launch()
        other_manager._upon_set_cell_checksum(
            reverse_fallback, checksum, False, True
        )

    def trigger_all_fallbacks(self, cell):
        checksum = cell._checksum
        reverse_fallbacks = self.livegraph.cell_to_reverse_fallbacks[cell]
        for reverse_fallback in reverse_fallbacks:
            self.trigger_fallback(checksum, reverse_fallback)

    ##########################################################################
    # API section V: Destruction
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
        self._last_ctx = None
        for path in list(self.livegraph.macropath_to_upstream.keys()):
            path.destroy()
        self.cachemanager.check_destroyed()
        self.livegraph.check_destroyed()
        self.taskmanager.check_destroyed()
        self.taskmanager.destroy()
        self.shareserver.destroy_manager(self)
        if not from_del:
            from ..macro_mode import _toplevel_managers, _toplevel_managers_temp
            _toplevel_managers.discard(self)
            _toplevel_managers_temp.discard(self)

    def __del__(self):
        self.destroy(from_del=True)

from .tasks import (
    SetCellValueTask, SetCellBufferTask,
    CellChecksumTask, GetBufferTask,
    DeserializeBufferTask, UponConnectionTask, UponBiLinkTask,
    CellUpdateTask
)

from ..protocol.calculate_checksum import checksum_cache
from ..protocol.deserialize import deserialize_cache, deserialize_sync
from ..protocol.get_buffer import get_buffer
from ..cache.buffer_cache import buffer_cache
from .unvoid import unvoid_cell
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro, Path, _global_paths
from ..reactor import Reactor
from .accessor import ReadAccessor
from ..structured_cell import StructuredCell
from .tasks.structured_cell import StructuredCellJoinTask, StructuredCellAuthTask
from ..utils import overlap_path
from ..protocol.deep_structure import DeepStructureError
from .cancel import get_scell_state
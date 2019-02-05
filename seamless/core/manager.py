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
    TransformCache, LabelCache, Accessor, Expression, TempRefManager, SemanticKey,
    cache_task_manager)
from .jobscheduler import JobScheduler
from .macro_mode import get_macro_mode, curr_macro
from ..mixed.io import deserialize as mixed_deserialize, serialize as mixed_serialize
from .runtime_reactor import RuntimeReactor
from .status import Status

import threading
import functools
import weakref
import traceback
import contextlib
import copy
import time
import itertools
import asyncio
from collections import namedtuple
from collections import OrderedDict
from weakref import WeakKeyDictionary
import sys

def main_thread_buffered(func):
    def not_destroyed_wrapper(self, func, *args, **kwargs):
        if self._destroyed:
            return
        func(self, *args, **kwargs)
    def main_thread_buffered_wrapper(self, *args, **kwargs):
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(not_destroyed_wrapper,
              self, func, *args, **kwargs
            )
            self.workqueue.append(work)
        else:
            if self._destroyed:
                return
            func(self, *args, **kwargs)
    return main_thread_buffered_wrapper

class Manager:
    _destroyed = False
    flushing = False
    def __init__(self, ctx):
        assert ctx._toplevel
        self.ctx = weakref.ref(ctx)
        self.unstable = set()
        # for now, just a single global workqueue
        from .mainloop import workqueue
        self.workqueue = workqueue
        self.flush_future = asyncio.ensure_future(self._flushloop())
        # for now, just a single global mountmanager
        from .mount import mountmanager
        self.mountmanager = mountmanager
        # caches
        self.cell_cache = CellCache(self)
        self.accessor_cache = AccessorCache(self)
        self.expression_cache = ExpressionCache(self)
        self.value_cache = ValueCache(self)
        self.label_cache = LabelCache(self)
        self.transform_cache = TransformCache(self)
        self.temprefmanager = TempRefManager()
        self.temprefmanager_future = asyncio.ensure_future(self.temprefmanager.loop())
        self.jobscheduler = JobScheduler(self)
        self.cache_task_manager = cache_task_manager

        self.status = {}
        self.reactors = WeakKeyDictionary() # RuntimeReactors
        self.jobs = {}  # jobid-to-job
        self.executing = {}  # level2-transformer-to-jobid
        self.scheduled = []  # list of type-schedop-(add/remove) tuples
                             # type = "transformer", schedop = level1 transformer
                             # type = "macro", schedop = Macro object
                             # type = "reactor", schedop = (Reactor object, pin name, expression)
        self._temp_tf_level1 = {}


    async def _schedule_transform_all(self, tf_level1, count, run_remote=True):
        """Runs until either a remote cache hit has been obtained, or a job has been submitted"""
        from .cache.transform_cache import TransformerLevel1
        assert isinstance(tf_level1, TransformerLevel1)
        tcache = self.transform_cache        
        result = tcache.get_result(tf_level1.get_hash())
        if result is not None:
            self.set_transformer_result(tf_level1, None, None, result, False)
            return
        task = None
        try:
            if run_remote:
                task = self.cache_task_manager.remote_transform_result(tf_level1.get_hash())
                if task is not None:
                    await task.future
                    result = task.future.result()
                    if result is not None:
                        self.set_transformer_result(tf_level1, None, None, result, False)
                        return
                task = None
                job = self.jobscheduler.schedule_remote(tf_level1, count)
                if job is not None:
                    return
            return await self._schedule_transform_job(tf_level1, count)
        except asyncio.CancelledError:
            if task is not None:
                task.cancel()

    async def _schedule_transform_job(self, tf_level1, count):
        from .cache.transform_cache import TransformerLevel1
        assert isinstance(tf_level1, TransformerLevel1)
        tcache = self.transform_cache
        tf_level2 = await tcache.build_level2(tf_level1)
        result = tcache.result_hlevel2.get(tf_level2.get_hash())
        if result is not None:
            self.set_transformer_result(tf_level1, tf_level2, None, result, False)
            return
        tcache.set_level2(tf_level1, tf_level2)  
        job = self.jobscheduler.schedule(tf_level2, count)
        return job

    async def run_remote_transform_job(self, tf_level1):
        tcache = self.transform_cache
        vcache = self.value_cache
        tcache.incref(tf_level1)
        hlevel1 = tf_level1.get_hash()        
        if hlevel1 not in tcache.transformer_from_hlevel1:
            tcache.transformer_from_hlevel1[hlevel1] = None
        try:
            coros = []
            for k in tf_level1._expressions:
                checksum = tf_level1._expressions[k].buffer_checksum
                coro = self.get_value_from_checksum_async(checksum)
                coros.append(coro)
            await asyncio.gather(*coros)
            for k in tf_level1._expressions:
                checksum = tf_level1._expressions[k].buffer_checksum
                assert vcache.get_buffer(checksum) is not None, (k, checksum.hex())
            job = await self._schedule_transform_all(tf_level1, 1, run_remote=False)
            if job.future is not None:
                await job.future                        
            k = list(tcache.result_hlevel1.keys())[0]
            result = tcache.get_result(hlevel1)
            return result
        finally:            
            #tcache.decref(tf_level1) #TODO: transformers that expire...
            real_transformer = tcache.transformer_from_hlevel1.pop(hlevel1, None)
            if real_transformer is not None:
                tcache.transformer_from_hlevel1[hlevel1] = real_transformer

    def schedule_jobs(self):
        if not len(self.scheduled):
            return
        if get_macro_mode():
            if curr_macro() is None:
                return
            else:
                raise NotImplementedError #TODO:
                # - Determine which paths are under active macro control
                # - Add those paths to scheduled_later; at the end, add set self.scheduled to scheduled_later
                # /TODO
        tcache = self.transform_cache
        scheduled_clean = OrderedDict()
        for type, schedop, add_remove in self.scheduled:
            key = type, schedop.get_hash()
            if key not in scheduled_clean:
                count = 0
            else:
                old_schedop, count = scheduled_clean[key]
                assert old_schedop.get_hash() == schedop.get_hash()
            dif = 1 if add_remove else -1
            scheduled_clean[key] = schedop, count + dif
        for key, value in scheduled_clean.items():
            type, _ = key
            schedop, count = value
            if count == 0:
                continue
            if type == "transformer":
                tf_level1 = schedop
                hlevel1 = tf_level1.get_hash()
                if count > 0:
                    for ttf, ttf_level1 in tcache.transformer_to_level1.items():
                        if ttf_level1.get_hash() != hlevel1:
                            continue
                        status = self.status[ttf]
                        if status.exec == "READY":
                            status.exec = "EXECUTING" 
                    task = self._schedule_transform_all(tf_level1, count)
                    self.cache_task_manager.schedule_task(
                        ("transform","all",tf_level1),task,count,
                        cancelfunc=None, resultfunc=None
                    )
                else:
                    task = self._schedule_transform_job(tf_level1, count)
                    self.cache_task_manager.schedule_task(
                        ("transform","job",tf_level1),task,count,
                        cancelfunc=None, resultfunc=None)
            elif type == "macro":
                raise NotImplementedError ### cache branch
            elif type == "reactor":
                raise NotImplementedError ### cache branch
            else:
                raise ValueError(type)
        self.scheduled = []
        self._temp_tf_level1.clear()


    def set_transformer_result_exception(self, level1, exception):
        #TODO: store exception
        transformer = None
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if tf_level1.get_hash() != hlevel1:
                continue
            if transformer is None:
                transformer = tf
            tstatus = self.status[tf]
            tstatus.exec = "ERROR"
            tstatus.data = "UNDEFINED"
            auth_status = None
            if tstatus.auth != "FRESH":
                auth_status = "FRESH"
                tstatus.auth = "FRESH"
            self.unstable.remove(tf)
            for cell in tcache.transformer_to_cells[tf]:
                self._propagate_status(cell,"UPSTREAM_ERROR", auth_status, full=False)
        
        if transformer is None:
            transformer = "<Unknown transformer>"                            
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n" + exc
        stars = "*" * 60 + "\n"
        print(stars + (msg % transformer) + stars, file=sys.stderr)

    def set_transformer_result(self, level1, level2, value, checksum, prelim):
        print("TODO: Manager.set_transformer_result: expand code properly, see evaluate.py")
        # TODO: this function is not checked for exceptions when called from a remote job...""
        #print("transformer result", value)
        assert value is not None or checksum is not None
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if tf_level1.get_hash() != hlevel1:
                continue
            tstatus = self.status[tf]
            tstatus.exec = "FINISHED"
            tstatus.data = "OK"
            tstatus.auth = "OBSOLETE" # To provoke an update
            for cell in tcache.transformer_to_cells[tf]:
                status = self.status[cell]
                if prelim:
                    if status.auth == "FRESH":
                        status.auth = "PRELIMINARY"
                else:
                    if status.auth == "PRELIMINARY":
                        status.auth = "FRESH"
                if value is not None:
                    self.set_cell(cell, value)
                    if checksum is None:
                        checksum = self.cell_cache.cell_to_buffer_checksums[cell]
                else:
                    self.set_cell_checksum(cell, checksum)
            self.update_transformer_status(tf,full=False)
        if checksum is None: #result conforms to no cell (probably remote transformation)
            checksum, buffer = protocol.calc_buffer(value)
            self.value_cache.incref(checksum, buffer, has_auth=False) 
        tcache.set_result(hlevel1, checksum)        
        if level2 is not None:
            tcache.result_hlevel2[level2.get_hash()] = checksum

    @main_thread_buffered
    def set_reactor_result(self, rtreactor, pinname, value):
        print("TODO: Manager.set_reactor_result: expand code properly, see evaluate.py")
        reactor = rtreactor.reactor()
        if pinname in rtreactor.output_dict:
            cells = rtreactor.output_dict[pinname]
        elif pinname in rtreactor.edit_dict:
            cells = [rtreactor.edit_dict[pinname]]
        else:
            raise ValueError(pinname)
        for cell in cells:
            status = self.status[cell]
            status.auth = "FRESH"
            self.set_cell(cell, value, origin=reactor)

    def set_reactor_exception(self, rtreactor, codename, exception):
        # TODO: store exception? log it?
        reactor = rtreactor.reactor()
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n" + exc
        stars = "*" * 60 + "\n"
        print(stars + (msg % (str(reactor)+":"+codename)) + stars, file=sys.stderr)

    def set_macro_exception(self, macro, exception):
        # TODO: store exception? log it?
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        msg = "Exception in %s:\n" + exc
        stars = "*" * 60 + "\n"
        print(stars + msg % str(macro) + stars, file=sys.stderr)

    async def _flush(self):
        self.flushing = True
        try:
            async for dummy in self.workqueue.flush():
                pass
        finally:
            self.flushing = False

    async def _flushloop(self):
        while 1:
            try:
                await self._flush()
            except:
                import traceback
                traceback.print_exc()
            await asyncio.sleep(0.1)

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
        self.expression_cache.expression_to_semantic_key[expression.get_hash()] = semantic_key
        return obj, semantic_key


    def get_expression(self, expression):
        if not isinstance(expression, Expression):
            raise TypeError(expression)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(expression.get_hash())
        cache_hit = False
        if semantic_key is not None:
            value = self.value_cache.get_object(semantic_key)
            if value is not None:
                cache_hit = True
        if not cache_hit:
            checksum = expression.buffer_checksum
            buffer_item = self.get_value_from_checksum(checksum)
            is_none = False
            if buffer_item is None:
                is_none = True
            else:
                _, _, buffer = buffer_item
                if buffer is None:
                    is_none = True
            if is_none:
                raise ValueError("Checksum not in value cache")            
            value, _ = self.cache_expression(expression, buffer)
        return value

    def build_expression(self, accessor):
        cell = accessor.cell
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            return None
        return accessor.to_expression(checksum)


    def get_default_accessor(self, cell):
        default_accessor = Accessor()
        default_accessor.celltype = cell._celltype
        default_accessor.storage_type = cell._storage_type
        default_accessor.cell = cell
        default_accessor.access_mode = cell._default_access_mode
        default_accessor.content_type = cell._content_type
        return default_accessor

    def cell_semantic_checksum(self, cell):
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)        
        if checksum is None:
            return None
        default_accessor = self.get_default_accessor(cell)
        default_expression = default_accessor.to_expression(checksum)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(default_expression.get_hash())
        if semantic_key is None:
            buffer_item = self.get_value_from_checksum(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = self.cache_expression(default_expression, buffer)
        semantic_checksum, _, _, _ = semantic_key
        return semantic_checksum        

    def value_get(self, checksum):
        """For communion server"""
        value = self.value_cache.get_buffer(checksum)[2]
        return value


    def register_cell(self, cell):
        if cell._celltype == "structured": raise NotImplementedError ### cache branch
        ccache = self.cell_cache
        ccache.cell_to_authority[cell] = True # upon registration, all cells are authoritative
        ccache.cell_to_accessors[cell] = []
        self.status[cell] = Status("cell")

    def register_transformer(self, transformer):
        tcache = self.transform_cache
        tcache.transformer_to_level0[transformer] = {}
        tcache.transformer_to_cells[transformer] = []
        self.status[transformer] = Status("transformer")

    def register_reactor(self, reactor):
        self.reactors[reactor] = RuntimeReactor(self, reactor)
        self.status[reactor] = Status("reactor")

    def register_macro(self, macro):
        self.status[macro] = Status("macro")

    def _schedule_transformer(self, transformer):
        tcache = self.transform_cache
        old_level1 = self._temp_tf_level1.get(transformer)
        if old_level1 is None:
            old_level1 = tcache.transformer_to_level1.get(transformer)
        new_level1 = tcache.build_level1(transformer)
        if old_level1 != new_level1:
            if old_level1 is not None:
                self.scheduled.append(("transformer", old_level1, False))
            self._temp_tf_level1[transformer] = new_level1
            tcache.set_level1(transformer, new_level1)
        self.scheduled.append(("transformer", new_level1, True))

    def _unschedule_transformer(self, transformer):
        tcache = self.transform_cache
        old_level1 = self._temp_tf_level1.get(transformer)
        if old_level1 is None:
            old_level1 = tcache.transformer_to_level1.get(transformer)
        if old_level1 is not None:
            self.scheduled.append(("transformer", old_level1, False))
            self._temp_tf_level1[transformer] = None

    def _propagate_status(self, cell, data_status, auth_status, full, origin=None):
        # "full" indicates a value change, but it is just propagated to update_worker
        from .reactor import Reactor
        if cell._celltype == "structured": raise NotImplementedError ### cache branch
        status = self.status[cell]
        new_data_status = status.data
        new_auth_status = status.auth
        if data_status is not None:
            dstatus = status.data            
            if data_status == "PENDING":
                if str(dstatus) in ("UNDEFINED", "UPSTREAM_ERROR"):
                    new_data_status = "PENDING"
            elif data_status == "UPSTREAM_ERROR":              
                if dstatus == "PENDING":
                    new_data_status = "UPSTREAM_ERROR"
        if auth_status is not None:
            new_auth_status = auth_status
        status.data = new_data_status
        status.auth = new_auth_status

        if full or new_auth_status is not None or new_data_status is not None:
            acache = self.accessor_cache
            accessors = itertools.chain(
                self.cell_cache.cell_to_accessors[cell],
                ( self.get_default_accessor(cell), ),
            )
            for accessor in accessors:
                haccessor = hash(accessor)
                for target_cell in acache.haccessor_to_cells.get(haccessor, []):
                    self._propagate_status(
                      target_cell, new_data_status, new_auth_status, full
                    )
                for worker in acache.haccessor_to_workers.get(haccessor, []):
                    if full and isinstance(worker, Reactor):
                        rtreactor = self.reactors[worker]
                        for pinname, accessor in rtreactor.input_dict.items():
                            if accessor.cell is cell:
                                rtreactor.updated.add(pinname)
                    self.update_worker_status(worker, full)
                
            if full:
                upstream = self.cell_cache.cell_from_upstream.get(cell)
                if isinstance(upstream, list):
                    for editpin in upstream:
                        reactor = editpin.worker_ref()
                        assert isinstance(reactor, Reactor)
                        if reactor is origin:
                            continue
                        rtreactor = self.reactors[reactor]
                        rtreactor.updated.add(editpin.name)
                        self.update_reactor_status(reactor, full=True)

    def update_transformer_status(self, transformer, full, new_connection=False):
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        if full:
            level1 = tcache.transformer_to_level1.pop(transformer, None)
            if level1 is not None:
                tcache.decref(level1)
        old_status = self.status[transformer]
        new_status = Status("transformer")
        new_status.data, new_status.exec, new_status.auth = "OK", "READY", "FRESH"
        if old_status is not None and old_status.exec == "FINISHED" and not full:
            new_status.exec = "FINISHED"
        for pin in transformer._pins:
            if transformer._pins[pin].io == "output":
                continue
            if pin not in accessor_dict:
                new_status.data = "UNCONNECTED"
                continue
            accessor = accessor_dict[pin]
            cell_status = self.status[accessor.cell]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        elif new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        
        backup_auth = None
        if full:
            if str(new_status.exec) in ("READY", "PENDING"):
                if old_status.exec == "FINISHED":
                    if new_status.auth == "FRESH":
                        backup_auth = new_status.auth  # to propagate downstream cells as obsolete;
                                                    # revert to backup_auth at the end of this function
                    new_status.auth = "OBSOLETE"
                elif old_status.exec == "BLOCKED":  
                    new_status.data = "PENDING"      

        self.status[transformer] = new_status
        propagate_data = (new_status.data != old_status.data)
        propagate_auth = (new_status.auth != old_status.auth)
        target_cells = tcache.transformer_to_cells[transformer]
        if new_status.exec == "FINISHED":
            if transformer in self.unstable:
                self.unstable.remove(transformer)
        elif new_status.exec == "READY":
            assert new_status.data in ("OK", "PENDING")
            self.unstable.add(transformer)
            if len(target_cells) and \
              ( str(new_status.auth) in ("FRESH", "OVERRULED") \
                or backup_auth is not None
              ):
                self._schedule_transformer(transformer)
        elif new_status.exec == "BLOCKED":
            if transformer in self.unstable:
                self.unstable.remove(transformer)
            if old_status.exec != "BLOCKED":
                self._unschedule_transformer(transformer)
        if propagate_data or propagate_auth or new_connection:
            data_status = new_status.data if propagate_data else None
            auth_status = new_status.auth if propagate_auth else None
            if new_connection and new_status.data == "OK":
                if str(new_status.exec) in ("PENDING", "READY", "EXECUTING"):
                    data_status = "PENDING"
            for cell in target_cells:                
                self._propagate_status(cell, data_status, auth_status, full=False)
            if backup_auth is not None:
                new_status.auth = backup_auth
            #print("UPDATE", transformer, old_status, "=>", new_status)


    def update_reactor_status(self, reactor, full):
        rtreactor = self.reactors[reactor]
        old_status = self.status[reactor]
        new_status = Status("reactor")
        new_status.data, new_status.exec, new_status.auth = "OK", "FINISHED", "FRESH"
        updated_pins = []
        for pinname, pin in reactor._pins.items():
            if pin.io in ("output", "edit"):
                continue
            accessor = rtreactor.input_dict[pinname]
            cell = accessor.cell
            cell_status = self.status[cell]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        if new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        elif new_status.data != "UNDEFINED":
            if full and len(rtreactor.updated) and rtreactor.live is not None:
                self.status[reactor] = new_status
                ok = rtreactor.execute()
                new_status = self.status[reactor]
                rtreactor.updated.clear()
        if old_status != new_status:
            #print("reactor update", reactor)
            #print("reactor status OLD", old_status, "(", old_status.data, old_status.exec, old_status.auth, ")")
            #print("reactor status NEW", new_status, "(", new_status.data, new_status.exec, new_status.auth, ")")            
            if not full:
                propagate_data = (new_status.data != old_status.data)
                propagate_auth = (new_status.auth != old_status.auth)
                data_status = new_status.data if propagate_data else None
                auth_status = new_status.auth if propagate_auth else None
                for pinname, pin in reactor._pins.items():
                    if pin.io != "output":
                        continue
                    for cell in rtreactor.output_dict[pinname]:
                        self._propagate_status(cell, data_status, auth_status, full=False)


    def update_macro_status(self, macro):
        old_status = self.status[macro]
        new_status = Status("macro")
        new_status.data, new_status.exec, new_status.auth = "OK", "FINISHED", "FRESH"
        updated_pins = []
        for pinname, pin in macro._pins.items():
            accessor = macro.input_dict[pinname]
            cell = accessor.cell
            cell_status = self.status[cell]

            s = cell_status.data_status
            if s == Status.StatusDataEnum.INVALID:
                s = Status.StatusDataEnum.UPSTREAM_ERROR
            if s.value > new_status.data_status.value:
                new_status.data_status = s

            s = cell_status.auth_status
            if s.value > new_status.auth_status.value:
                new_status.auth_status = s
        
        if new_status.data_status.value > Status.StatusDataEnum.PENDING.value:
            new_status.exec = "BLOCKED"
        if new_status.data_status.value == Status.StatusDataEnum.PENDING.value:
            new_status.exec = "PENDING"
        elif new_status.data != "UNDEFINED":
            self.status[macro] = new_status
            macro._execute()
            new_status = self.status[macro]
        if old_status != new_status:
            self.status[macro] = new_status

    def update_worker_status(self, worker, full):
        from . import Transformer, Reactor, Macro
        if isinstance(worker, Transformer):
            return self.update_transformer_status(worker, full=full)
        elif isinstance(worker, Reactor):
            rtreactor = self.reactors[worker]
            for pinname, pin in worker._pins.items():
                if pin.io == "input":
                    io_dict = rtreactor.input_dict
                elif pin.io == "output":
                    io_dict = rtreactor.output_dict
                elif pin.io == "edit":
                    io_dict = rtreactor.edit_dict
                if pinname not in io_dict:
                    break
            else:
                return self.update_reactor_status(worker, full=full)
        elif isinstance(worker, Macro):
            return self.update_macro_status(worker)
        else:
            raise TypeError(worker)

    def _connect_cell_transformer(self, cell, pin):
        """Connects cell to transformer inputpin"""
        transformer = pin.worker_ref()
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        assert pin.name not in accessor_dict, pin #double connection
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )

        if io == "input":
            pass
        elif io == "output":
            raise TypeError(pin) #outputpin, cannot connect a cell to that...
        else:
            raise TypeError(pin)

        accessor = self.get_default_accessor(cell)
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [transformer]
        else:
            acache.haccessor_to_workers[haccessor].append(transformer)
        accessor_dict[pin.name] = accessor
        self.update_transformer_status(transformer,full=False)

    def _connect_reactor(self, pin, cell, inout):
        """Connects cell to/from reactor pin"""
        reactor = pin.worker_ref()
        rtreactor = self.reactors[reactor]        
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )

        if io == "input":
            if not inout == "in":
                raise TypeError(pin) # input pin must be the target
        elif io == "edit":
            pass # pin.connect(cell) and cell.connect(pin) are equivalent
        elif io == "output":
            if inout == "in":
                raise TypeError(pin) # output pin cannot be the target
        else:
            raise TypeError(pin)
        
        if io == "edit":
            if pin.name in rtreactor.edit_dict:
                raise TypeError(pin) #Edit pin can connect to only one cell
            current_upstream = self.cell_cache.cell_from_upstream.get(cell)
            if current_upstream is None:
                current_upstream = []
                self.cell_cache.cell_from_upstream[cell] = current_upstream
            if not isinstance(current_upstream, list):
                raise TypeError("Cell %s is already connected to %s" % (cell, current_upstream))                
            self.cell_cache.cell_from_upstream[cell].append(pin)
            rtreactor.edit_dict[pin.name] = cell
        elif inout == "in":
            assert pin.name not in rtreactor.input_dict, pin #double connection
            accessor = self.get_default_accessor(cell)
            if access_mode is not None and access_mode != accessor.access_mode:
                accessor.source_access_mode = accessor.access_mode
                accessor.access_mode = access_mode
            if content_type is not None and content_type != accessor.content_type:
                accessor.source_content_type = accessor.content_type
                accessor.content_type = content_type
            acache = self.accessor_cache
            haccessor = hash(accessor)
            if haccessor not in acache.haccessor_to_workers:
                acache.haccessor_to_workers[haccessor] = [reactor]
            else:
                acache.haccessor_to_workers[haccessor].append(reactor)
            rtreactor.input_dict[pin.name] = accessor
        elif inout == "out":
            output_dict = rtreactor.output_dict
            if not pin.name in output_dict:
                output_dict[pin.name] = []
            output_dict[pin.name].append(cell)
        else:
            raise ValueError(inout)

        for pinname, pin in reactor._pins.items():
            if pin.io == "input":
                io_dict = rtreactor.input_dict
            elif pin.io == "output":
                io_dict = rtreactor.output_dict
            elif pin.io == "edit":
                io_dict = rtreactor.edit_dict
            if pinname not in io_dict:
                break
        else:
            rtreactor.live = False
            rtreactor.updated = set(reactor._pins.keys())
            self.update_reactor_status(reactor, full=True)


    def _connect_cell_macro(self, cell, pin):
        """Connects cell to macro pin"""
        macro = pin.worker_ref()
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )

        if io != "input":
            raise TypeError(pin) # input pin must be the target

        assert pin.name not in macro.input_dict, pin #double connection
        accessor = self.get_default_accessor(cell)
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [macro]
        else:
            acache.haccessor_to_workers[haccessor].append(macro)
        macro.input_dict[pin.name] = accessor

        for pinname, pin in macro._pins.items():
            if pinname not in macro.input_dict:
                break
        else:
            self.update_macro_status(macro)

    def connect_cell(self, cell, other):
        #print("connect_cell", cell, other)
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .worker import PinBase
        if not isinstance(cell, Cell):
            raise TypeError(cell)
        if isinstance(other, Link):
            other = other.get_linked()
        if isinstance(other, PinBase):
            worker = other.worker_ref()
            if isinstance(worker, Transformer):
                self._connect_cell_transformer(cell, other)
            elif isinstance(worker, Reactor):
                self._connect_reactor(other, cell, "in")
            elif isinstance(worker, Macro):
                self._connect_cell_macro(cell, other)
            else:
                raise TypeError(type(worker))
        elif isinstance(other, Cell):
            raise NotImplementedError ###cache branch
        else:
            raise TypeError(type(other))
        self.schedule_jobs()

    def cell_from_pin(self, pin):
        from . import Transformer, Reactor, Macro
        from .worker import InputPin, OutputPin, EditPin
        worker = pin.worker_ref()
        if worker is None:
            raise ValueError("Worker has died")
        if isinstance(worker, Transformer):            
            if isinstance(pin, InputPin):
                accessor_dict = self.transform_cache.transformer_to_level0[worker]
                return accessor_dict.get(pin.name)
            elif isinstance(pin, OutputPin):
                return self.transform_cache.transformer_to_cells.get(worker, [])
            else:
                raise TypeError(pin)
        elif isinstance(worker, Reactor):
            rt_reactor = self.reactors[worker]
            if isinstance(pin, InputPin):
                accessor = rt_reactor.input_dict.get(pin.name)
                if accessor is None:
                    return None
                else:
                    return accessor.cell
            elif isinstance(pin, EditPin):
                return rt_reactor.edit_dict.get(pin.name)
            elif isinstance(pin, OutputPin):
                return rt_reactor.output_dict.get(pin.name, [])
            else:
                raise TypeError(pin)
        elif isinstance(worker, Macro):
            raise NotImplementedError ### cache branch
        else:
            raise TypeError(worker)


    def connect_pin(self, pin, cell):
        #print("connect_pin", pin, cell)
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .worker import PinBase, InputPin, OutputPin, EditPin
        if isinstance(cell, Link):
            cell = cell.get_linked()
        if not isinstance(cell, Cell):
            raise TypeError(cell)
        if not isinstance(pin, PinBase) or isinstance(pin, InputPin):
            raise TypeError(pin)
        if isinstance(pin, EditPin):
            if not isinstance(worker, Reactor):
                raise TypeError((pin, worker)) # Editpin must be connected to reactor
        else:    
            current_upstream = self.cell_cache.cell_from_upstream.get(cell)
            if current_upstream is not None:
                raise TypeError("Cell %s is already connected to %s" % (cell, current_upstream))
            self.cell_cache.cell_from_upstream[cell] = pin

        worker = pin.worker_ref()
        if isinstance(worker, Transformer):
            self.transform_cache.transformer_to_cells[worker].append(cell)            
            self.update_transformer_status(worker,full=False, new_connection=True)
        elif isinstance(worker, Macro):
            raise NotImplementedError ###cache branch
        elif isinstance(worker, Reactor):
            self._connect_reactor(pin, cell, "out")
        else:
            raise TypeError(worker)
        self.schedule_jobs()

    def _update_status(self, cell, checksum, *, has_auth, origin):
        status = self.status[cell]
        old_data_status = status.data
        old_auth_status = status.auth
        if checksum is None:
            status.data = "UNDEFINED"
        else:
            status.data = "OK"
        if not has_auth:
            status.auth = "OVERRULED"
        new_data_status = status.data if status.data != old_data_status else None
        new_auth_status = status.auth if status.auth != old_auth_status else None
        self._propagate_status(
            cell, new_data_status, new_auth_status, 
            full=True, origin=origin
        )
        self.schedule_jobs()

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
            self._update_status(cell, checksum, has_auth=has_auth, origin=None)

    @main_thread_buffered
    def set_cell(self, cell, value, *, from_buffer=False, origin=None):
        # "origin" indicates the worker that generated the .set_cell call
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
            self.expression_cache.expression_to_semantic_key[default_expression.get_hash()] = semantic_key
            if not is_dummy_mount(cell._mount):
                if not get_macro_mode():
                    self.mountmanager.add_cell_update(cell)
            self._update_status(cell, checksum, has_auth=has_auth, origin=origin)
        else:
            # Just refresh the semantic key timeout
            vcache.add_semantic_key(semantic_key, obj)

    @main_thread_buffered
    def set_cell_label(self, cell, label):
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            raise ValueError("cell is undefined")
        self.label_cache.set(label, checksum)

    def get_cell_label(self, cell):
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            return None
        return self.label_cache.get_label(checksum)

    def get_checksum_from_label(self, label):
        checksum = self.label_cache.get_checksum(label)
        if checksum is None:
            cache_task = self.cache_task_manager.remote_checksum_from_label(label)
            if cache_task is None:
                return None
            cache_task.join()
            checksum = self.label_cache.get_checksum(label)  #  Label will now have been added to cache
        return checksum

    def get_value_from_checksum(self, checksum):
        buffer_item = self.value_cache.get_buffer(checksum)
        if buffer_item is None:
            cache_task = self.cache_task_manager.remote_value(checksum)
            if cache_task is None:
                return None
            cache_task.join()
            buffer_item = self.value_cache.get_buffer(checksum)
        return buffer_item
        
    async def get_value_from_checksum_async(self, checksum):
        buffer_item = self.value_cache.get_buffer(checksum)        
        if buffer_item is None:
            cache_task = self.cache_task_manager.remote_value(checksum)            
            if cache_task is None:
                return None
            await cache_task.future
            buffer_item = self.value_cache.get_buffer(checksum)
        return buffer_item
                
    @main_thread_buffered
    def set_cell_from_label(self, cell, label):        
        checksum = self.get_checksum_from_label(label)
        if checksum is None:
            raise Exception("Label has no checksum")
        return self.set_cell_checksum(cell, checksum)


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
        self.schedule_jobs()

    async def equilibrate(self, timeout, report, path):        
        delta = None
        if timeout is not None:
            deadline = time.time() + timeout
        lpath = len(path)
        def get_unstable():
            return {w for w in self.unstable if w.path[:lpath] == path}
        while 1:
            unstable = get_unstable()
            if not len(unstable):
                break
            if timeout is not None:
                remain = deadline - time.time()
                if remain <= 0:
                    break
                if delta is None or remain < delta:
                    delta = remain
            if report is not None:
                if delta is None or report < delta:
                    delta = report
            cache_jobs = []
            for k,v in self.cache_task_manager.tasks.items():
                cache_jobs.append(v.future)
            if len(cache_jobs):
                await asyncio.gather(*cache_jobs)
            self.jobscheduler.cleanup()
            unstable = get_unstable()
            if not len(unstable):
                break
            jobs = []
            for job in itertools.chain(
                  self.jobscheduler.jobs.values(),
                  self.jobscheduler.remote_jobs.values(),
                ):
                jobs.append(job.future)
                                    
            if not len(jobs):
                raise Exception("No jobs, but unstable workers: %s" % unstable)
            if delta is None:
                await asyncio.gather(*jobs)
            else:
                await asyncio.wait(jobs, timeout=delta)
                if report is not None:
                    unstable = get_unstable()                    
                    if len(unstable):
                        unstable = sorted(unstable,key=lambda w:w.path)
                        print("Waiting for:", unstable)
        return self.unstable

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self.temprefmanager_future.cancel()
        self.flush_future.cancel()

    def __del__(self):
        self.destroy()
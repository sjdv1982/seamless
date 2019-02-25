"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

NOTE: connection methods now accept a "subpath" as an extra argument
Normal cells (cell.Cell) always have subpath=None; specifying subpath is principally
 done by StructuredCell channels.

From the manager's point of view, it is assumed that subpaths are *independent*:
- A cell with input/edit subpath ('a',), does not have an additional input/edit subpath ('a', 'b')
- For a cell with output subpaths ('a',) and ('a', 'b'), the manager will be informed of updates 
  to each channel separately; sending an update to ('a',) is not enough.
Manager does NOT verify independence; it is the responsibility of the caller
 (i.e. StructuredCell) to do so.
In addition, cell values are set as a whole: set_cell should only be invoked with subpath=None
Exception: deep cells
"""

from . import protocol
from .protocol.deserialize import deserialize
from .cache import (CellCache, AccessorCache, ExpressionCache, ValueCache,
    TransformCache, LabelCache, Accessor, Expression, TempRefManager, SemanticKey,
    cache_task_manager)
from .jobscheduler import JobScheduler
from .macro_mode import get_macro_mode, curr_macro
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
import numpy as np

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
        self.stream_status = {}
        self.reactors = WeakKeyDictionary() # RuntimeReactors
        self.jobs = {}  # jobid-to-job
        self.executing = {}  # level2-transformer-to-jobid
        self.scheduled = []  # list of type-schedop-(add/remove) tuples
                             # type = "transformer", schedop = level1 transformer
                             # type = "macro", schedop = Macro object
                             # type = "reactor", schedop = (Reactor object, pin name, expression)
        self._temp_tf_level1 = {}
        self.cell_to_cell = [] # list of (source-accessor-or-pathtuple, target-accessor-or-pathtuple); pathtuples are (Path, subpath)


    async def _schedule_transform_all(self, tf_level1, count, from_remote=False):
        """Runs until either a remote cache hit has been obtained, or a job has been submitted"""
        from .cache.transform_cache import TransformerLevel1
        assert isinstance(tf_level1, TransformerLevel1)
        tcache = self.transform_cache
        htf_level1 = tf_level1.get_hash()
        result = tcache.get_result(htf_level1)
        if result is not None:
            self.set_transformer_result(tf_level1, None, None, result, False)
            return
        task = None
        try:
            if not from_remote:
                task = self.cache_task_manager.remote_transform_result(htf_level1)
                if task is not None:
                    await task.future
                    result = task.future.result()
                    if result is not None:
                        self.set_transformer_result(tf_level1, None, None, result, False)
                        return
                try:
                    tf_level2 = await tcache.build_level2(tf_level1)
                except ValueError:
                    pass
                else:                    
                    htf_level2 = tf_level2.get_hash()
                    result = tcache.get_result_level2(htf_level2)
                    if result is not None:
                        self.set_transformer_result(tf_level1, tf_level2, None, result, False)
                        return
                    task = self.cache_task_manager.remote_transform_result_level2(tf_level2.get_hash())
                    if task is not None:
                        await task.future
                        result = task.future.result()
                        if result is not None:
                            self.set_transformer_result(tf_level1, tf_level2, None, result, False)
                            return
                task = None
                job = self.jobscheduler.schedule_remote(tf_level1, count)
                if job is not None:
                    return
                if tcache.transformer_from_hlevel1.get(htf_level1) is None: # job must have been cancelled
                    return
            return await self._schedule_transform_job(tf_level1, count, from_remote=from_remote)
        except asyncio.CancelledError:
            if task is not None:
                task.cancel()

    async def _schedule_transform_job(self, tf_level1, count, from_remote=False, from_stream=False):
        from .cache.transform_cache import TransformerLevel1
        assert isinstance(tf_level1, TransformerLevel1)
        if tf_level1._stream_params is not None:
            return await self._schedule_transform_stream_job(tf_level1, count, from_remote=from_remote)
        tcache = self.transform_cache
        tf_level2 = await tcache.build_level2(tf_level1)
        tcache.set_level2(tf_level1, tf_level2)
        result = tcache.result_hlevel2.get(tf_level2.get_hash())
        if result is not None:            
            self.set_transformer_result(tf_level1, tf_level2, None, result, False)
            return
        transformer_can_be_none = from_remote or from_stream
        job = self.jobscheduler.schedule(tf_level2, count, transformer_can_be_none)
        return job

    async def _schedule_transform_stream_job(self, tf_level1, count, from_remote=False):
        from .cache.transform_cache import TransformerLevel1
        tcache = self.transform_cache
        stream_params = tf_level1._stream_params
        if len(stream_params) > 1: raise NotImplementedError
        for k,v in stream_params.items():
            if v != "map": raise NotImplementedError
        k = list(stream_params.keys())[0]
        expressions = copy.deepcopy(tf_level1._expressions)
        e = expressions[k]
        value = self.get_expression(e)
        if isinstance(value, (list, np.ndarray)):
            items = range(len(value))
        elif isinstance(value, dict):
            items = value.keys()
        old_subpath = () if e.subpath is None else e.subpath
        items_level1 = {}
        stream_status = self.stream_status
        transformers = []
        hlevel1 = tf_level1.get_hash()
        for ttf, ttf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if ttf_level1.get_hash() != hlevel1:
                continue
            transformers.append(ttf)
        job_coros = []
        for item in items:
            e.subpath = old_subpath + (item,)
            item_level1 = TransformerLevel1(expressions, None, tf_level1.output_name)
            tcache.incref(item_level1)
            items_level1[item] = item_level1            
        for tf in transformers:
            tcache.stream_transformer_to_levels1[tf] = copy.copy(items_level1)
        
        for item in items:
            item_level1 = items_level1[item]
            for tf in transformers:
                stream_status[tf, item] = copy.deepcopy(self.status[tf])
            job_coro = self._schedule_transform_job(
                item_level1, count, from_remote=from_remote, from_stream=True
            )
            job_coros.append(job_coro)
        jobs = []
        if len(job_coros):
            jobs0 = await asyncio.gather(*job_coros)
            for job in jobs0:
                if job is not None:   
                    jobs.append(job)
        return self.jobscheduler.jobarray(jobs)

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
            job = await self._schedule_transform_all(tf_level1, 1, from_remote=True)
            if job is not None and job.future is not None:
                await job.future                        
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
                    for ttf, ttf_levels1 in tcache.stream_transformer_to_levels1.items():
                        for k, ttf_level1 in ttf_levels1.items():
                            if ttf_level1.get_hash() != hlevel1:
                                continue
                            status = self.stream_status[ttf, k]
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
            else:
                raise ValueError(type)
        self.scheduled = []
        self._temp_tf_level1.clear()


    def set_transformer_result_exception(self, level1, level2, exception):
        #TODO: store exception
        transformer = None
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        hlevel2 = None
        if level2 is not None:
            hlevel2 = level2.get_hash()
        transformers = []
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            htflevel1 = tf_level1.get_hash()
            if htflevel1 != hlevel1:
                if hlevel2 is None:
                    continue
                if htflevel1 not in tcache.hlevel1_to_level2:
                    continue
                if tcache.hlevel1_to_level2[htflevel1].get_hash() != hlevel2:
                    continue
            if transformer is None:
                transformer = tf, None
            transformers.append((tf, None))
        for tf, tf_levels1 in list(tcache.stream_transformer_to_levels1.items()): #could be more efficient...            
            for k, tf_level1 in tf_levels1.items():                
                htflevel1 = tf_level1.get_hash()
                if htflevel1 != hlevel1:
                    if hlevel2 is None:
                        continue
                    if htflevel1 not in tcache.hlevel1_to_level2:
                        continue
                    if tcache.hlevel1_to_level2[htflevel1].get_hash() != hlevel2:
                        continue
                if transformer is None:
                    transformer = tf, k
                transformers.append((tf, k))
        for tf, k in transformers:
            if k is None:
                tstatus = self.status[tf]
            else:
                tstatus = self.stream_status[tf, k]
            tstatus.exec = "ERROR"
            tstatus.data = "UNDEFINED"
            auth_status = None
            if tstatus.auth != "FRESH":
                auth_status = "FRESH"
                tstatus.auth = "FRESH"
            self.unstable.discard(tf)
            for cell, subpath in tcache.transformer_to_cells[tf]:
                self._propagate_status(
                  cell,"UPSTREAM_ERROR", auth_status, 
                  cell_subpath=subpath, full=False
                )
        
        if transformer is None:
            transformer = "<Unknown transformer>", None
        exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
        exc = "".join(exc)
        kstr = "" if transformer is None else ", stream element %s" % transformer[1]
        msg = "Exception in %s%s:\n" % (transformer[0], kstr) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)

    def set_transformer_result(self, level1, level2, value, checksum, prelim):
        from .link import Link
        from .macro import Path
        print("TODO: Manager.set_transformer_result: expand code properly, see evaluate.py")
        # TODO: this function is not checked for exceptions when called from a remote job...""
        assert value is not None or checksum is not None        
        if self._destroyed:
            return
        tcache = self.transform_cache
        hlevel1 = level1.get_hash()
        for tf, tf_level1 in list(tcache.transformer_to_level1.items()): #could be more efficient...
            if tf_level1.get_hash() != hlevel1:
                continue
            tstatus = self.status[tf]
            tstatus.exec = "FINISHED"
            tstatus.data = "OK"
            tstatus.auth = "OBSOLETE" # To provoke an update
            for cell, subpath in tcache.transformer_to_cells[tf]:
                if isinstance(cell, Link):
                    cell = cell.linked()
                if isinstance(cell, Path):
                    cell = cell._cell
                    if cell is None:
                        continue    
                status = self.status[cell][subpath]
                if prelim:
                    if status.auth == "FRESH":
                        status.auth = "PRELIMINARY"
                else:
                    if status.auth == "PRELIMINARY":
                        status.auth = "FRESH"
                if value is not None:
                    # TODO: dirty...
                    value2 = value
                    if cell._celltype == "mixed":
                        from ..mixed.get_form import get_form
                        storage, form = get_form(value)
                        value2 = (storage, form, value)
                    self.set_cell(cell, value2, subpath=subpath)
                    if checksum is None and subpath is not None:
                        checksum = self.cell_cache.cell_to_buffer_checksums[cell]
                else:
                    if subpath is not None: raise NotImplementedError ###either streams, or deep cells
                    if cell._destroyed:
                        raise Exception(cell.name)
                    self.set_cell_checksum(cell, checksum)
            self.update_transformer_status(tf,full=False)
        if checksum is None: #result conforms to no cell (remote transformation, stream transformation, or subpath)
            checksum, buffer = protocol.calc_buffer(value)
            self.value_cache.incref(checksum, buffer, has_auth=False) 
        tcache.set_result(hlevel1, checksum)
        if level2 is not None:
            tcache.set_result_level2(level2.get_hash(), checksum)
        if not prelim:
            for tf, tf_levels1 in list(tcache.stream_transformer_to_levels1.items()): #could be more efficient...
                for k, tf_level1 in tf_levels1.items():
                    if tf_level1.get_hash() != hlevel1:
                        continue
                    self.set_transformer_stream_result(tf, k)        
        self.schedule_jobs()

    def set_transformer_stream_result(self, tf, k):
        """Set one element k of a stream transformer result"""
        tcache = self.transform_cache
        vcache = self.value_cache
        tstatus = self.stream_status[tf, k]
        tstatus.exec = "FINISHED"
        tstatus.data = "OK"
        tf_levels1 = tcache.stream_transformer_to_levels1[tf]        
        for k2, tf_level1 in tf_levels1.items():
            tstatus2 = self.stream_status[tf, k2]
            if tstatus2 != "FINISHED":
                break
        else:
            result = {}
            for k2, tf_level1 in tf_levels1.items():
                k2_checksum = tcache.get_result(tf_level1.get_hash())
                k2_buffer = self.value_cache.get_buffer(k2_checksum)[2]
                k2_result = deserialize(
                    "mixed", None,  (),
                    k2_buffer, from_buffer=True, buffer_checksum=k2_checksum,
                    source_access_mode=None, 
                    source_content_type=None
                )
                k2_value = k2_result[2][2]
                result[k2] = k2_value
            if isinstance(k, int):
                result = [result[n] for n in range(len(result))]
            level1 = tcache.transformer_to_level1[tf]
            self.set_transformer_result(level1, None, result, None, False)

        #raise NotImplementedError

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
        for cell, subpath in cells:
            status = self.status[cell][subpath]
            status.auth = "FRESH"
            self.set_cell(cell, value, origin=reactor, subpath=subpath)
        self.schedule_jobs()

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
        msg = "Exception in %s:\n"% str(macro) + exc
        stars = "*" * 60 + "\n"
        print(stars + msg + stars, file=sys.stderr)

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


    def get_id(self):
        self._ids += 1
        return self._ids

    def cache_expression(self, expression, buffer):
        """Generates object value cache and semantic key for expression
        Invoke this routine in cache of a partial value cache miss, i.e.
        the buffer checksum is a hit, but the semantic key is either
        unknown or has expired from object cache"""

        semantic_obj, semantic_key = protocol.evaluate_from_buffer(expression, buffer)
        self.value_cache.add_semantic_key(semantic_key, semantic_obj)
        self.expression_cache.expression_to_semantic_key[expression.get_hash()] = semantic_key
        return semantic_obj, semantic_key


    def get_expression(self, expression):
        if not isinstance(expression, Expression):
            raise TypeError(expression)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(expression.get_hash())
        cache_hit = False
        if semantic_key is not None:
            semantic_value = self.value_cache.get_object(semantic_key)
            if semantic_value is not None:
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
            semantic_value, _ = self.cache_expression(expression, buffer)
        return semantic_value

    def build_expression(self, accessor):
        cell = accessor.cell
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            return None
        return accessor.to_expression(checksum)


    def get_default_accessor(self, cell):
        from .cell import Cell
        if not isinstance(cell, Cell):
            raise TypeError(cell)
        default_accessor = Accessor()
        default_accessor.celltype = cell._celltype
        default_accessor.storage_type = cell._storage_type
        default_accessor.cell = cell
        default_accessor.access_mode = cell._default_access_mode
        default_accessor.content_type = cell._content_type
        return default_accessor

    def cell_semantic_checksum(self, cell, subpath):
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)        
        if checksum is None:
            return None
        accessor = self.get_default_accessor(cell)
        accessor.subpath = subpath
        expression = accessor.to_expression(checksum)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(expression.get_hash())
        if semantic_key is None:
            buffer_item = self.get_value_from_checksum(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = self.cache_expression(expression, buffer)
        semantic_checksum, _, _ = semantic_key
        return semantic_checksum        

    def value_get(self, checksum):
        """For communion server"""
        value = self.value_cache.get_buffer(checksum)[2]
        return value


    def register_cell(self, cell):
        ccache = self.cell_cache
        ccache.cell_to_authority[cell] = {None: True} # upon registration, all cells are authoritative
        ccache.cell_to_accessors[cell] = {None : []}
        self.status[cell] = {None: Status("cell")}

    def _register_cell_paths(self, cell, paths, has_auth):
        ccache = self.cell_cache
        for path in paths:
            ccache.cell_to_authority[cell][path] = has_auth
            ccache.cell_to_accessors[cell][path] = []
            self.status[cell][path] = Status("cell")

    def register_structured_cell(self, structured_cell):
        ccache = self.cell_cache
        cell = structured_cell.cell
        assert cell in ccache.cell_to_authority
        raise NotImplementedError ### cache branch; self._register_cell_paths with authority info

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

    def _propagate_status(self, cell, data_status, auth_status, full, *, cell_subpath, origin=None):
        # "full" indicates a value change, but it is just propagated to update_worker
        # print("propagate status", cell, cell_subpath, data_status, auth_status, full)
        from .reactor import Reactor
        from .macro import Path
        if isinstance(cell, Path):
            cell = cell._cell
            if cell is None:
                return
        if cell._celltype == "structured": 
            raise TypeError
        status = self.status[cell][cell_subpath]
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
                self.cell_cache.cell_to_accessors[cell][cell_subpath],
                [self.get_default_accessor(cell)],
            )
            for accessor in accessors:
                haccessor = hash(accessor)
                for worker, acc in acache.haccessor_to_workers.get(haccessor, []):
                    if acc is None:
                        acc = accessor
                    else:
                        if acc.cell is not cell:
                            continue
                    if full and isinstance(worker, Reactor):
                        rtreactor = self.reactors[worker]
                        for pinname, accessor2 in rtreactor.input_dict.items():
                            if accessor2.cell is cell:
                                rtreactor.updated.add(pinname)
                    if not worker._active: return ###TODO: should not happen (and so far, doesn't seem to)
                    self.update_worker_status(worker, full)
            self.update_cell_to_cells(
              cell, data_status, auth_status, 
              full=full, origin=origin,subpath=cell_subpath
            )
            if full:
                upstream = None
                upstream0 = self.cell_cache.cell_from_upstream.get(cell)
                if upstream0 is not None:
                    upstream = upstream0.get(cell_subpath)
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
        if transformer._destroyed: return ### TODO, shouldn't happen...
        if not transformer._active: return ### TODO, shouldn't happen...
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
            cell_status = self.status[accessor.cell][accessor.subpath]

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
            self.unstable.discard(transformer)
        elif new_status.exec == "READY":
            assert new_status.data in ("OK", "PENDING")
            if len(target_cells) and \
              ( str(new_status.auth) in ("FRESH", "OVERRULED") \
                or backup_auth is not None
              ):
                self.unstable.add(transformer)
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
            for cell, subpath in target_cells:                
                self._propagate_status(cell, data_status, auth_status, 
                  full=False, cell_subpath=subpath
                )
            if backup_auth is not None:
                new_status.auth = backup_auth
            #print("UPDATE", transformer, old_status, "=>", new_status)


    def update_reactor_status(self, reactor, full):
        if reactor._destroyed: return ### TODO, shouldn't happen...
        if not reactor._active: return ### TODO, shouldn't happen...
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
            subpath = accessor.subpath
            cell_status = self.status[cell][subpath]

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
                    for cell, subpath in rtreactor.output_dict[pinname]:
                        self._propagate_status(cell, data_status, auth_status, full=False, cell_subpath=subpath)


    def update_macro_status(self, macro):
        if macro._destroyed: return ### TODO, shouldn't happen...
        if not macro._active: return ### TODO, shouldn't happen...
        old_status = self.status[macro]
        new_status = Status("macro")
        new_status.data, new_status.exec, new_status.auth = "OK", "FINISHED", "FRESH"
        updated_pins = []
        for pinname, pin in macro._pins.items():
            accessor = macro.input_dict[pinname]
            cell = accessor.cell
            subpath = accessor.subpath
            cell_status = self.status[cell][subpath]

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
            raise TypeError(worker, type(worker))

    def _verify_connect(self, source, target):
        from .macro import Path
        assert source._root()._manager is self
        assert source._root() is target._root()
        source_macro = source._get_macro()
        target_macro = target._get_macro()
        current_macro = curr_macro()
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

    def _connect_cell_transformer(self, cell, pin, cell_subpath):
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
        acc = None
        if cell_subpath is not None:
            accessor.subpath = cell_subpath
            acc = accessor
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
            acc = accessor
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
            acc = accessor
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [(transformer, acc)]
        else:
            acache.haccessor_to_workers[haccessor].append((transformer, acc))
        accessor_dict[pin.name] = accessor
        self.update_transformer_status(transformer,full=False)

    def _connect_reactor(self, pin, cell, inout, cell_subpath):
        """Connects cell to/from reactor pin"""
        current_upstream = self.cell_cache.cell_from_upstream.get(cell)

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
                current_upstream = {}
                self.cell_cache.cell_from_upstream[cell] = current_upstream
            current_upstream2 = current_upstream.get(cell_subpath)
            if current_upstream2 is None:
                current_upstream2 = []
                current_upstream[cell_subpath] = current_upstream2
            if not isinstance(current_upstream2, list):
                raise TypeError("Cell %s is already connected to %s" % (cell, current_upstream2))
            current_upstream2.append(pin)
            rtreactor.edit_dict[pin.name] = (cell,cell_subpath)
        elif inout == "in":
            assert pin.name not in rtreactor.input_dict, pin #double connection
            accessor = self.get_default_accessor(cell)
            acc = None
            if cell_subpath is not None:
                accessor.subpath = cell_subpath
                acc = accessor
            if access_mode is not None and access_mode != accessor.access_mode:
                accessor.source_access_mode = accessor.access_mode
                accessor.access_mode = access_mode
                acc = accessor
            if content_type is not None and content_type != accessor.content_type:
                accessor.source_content_type = accessor.content_type
                accessor.content_type = content_type
                acc = accessor
            acache = self.accessor_cache
            haccessor = hash(accessor)
            if haccessor not in acache.haccessor_to_workers:
                acache.haccessor_to_workers[haccessor] = [(reactor,acc)]
            else:
                acache.haccessor_to_workers[haccessor].append((reactor,acc))
            rtreactor.input_dict[pin.name] = accessor
        elif inout == "out":
            current_upstream = self.cell_cache.cell_from_upstream.get(cell)
            if current_upstream is None:
                current_upstream = {}
                self.cell_cache.cell_from_upstream[cell] = current_upstream
            current_upstream2 = current_upstream.get(cell_subpath)
            if current_upstream2 is not None:
                raise TypeError("%s is already connected from %s" % (cell, current_upstream2))
            current_upstream[cell_subpath] = pin
            output_dict = rtreactor.output_dict
            if not pin.name in output_dict:
                output_dict[pin.name] = []
            output_dict[pin.name].append((cell, cell_subpath))
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


    def _connect_cell_macro(self, cell, pin, cell_subpath):
        """Connects cell to macro pin"""
        macro = pin.worker_ref()
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )

        if io != "input":
            raise TypeError(pin) # input pin must be the target

        assert pin.name not in macro.input_dict, pin #double connection
        accessor = self.get_default_accessor(cell)
        acc = None
        if cell_subpath is not None:
            accessor.subpath = cell_subpath
            acc = accessor
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
            acc = accessor
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
            acc = accessor
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [(macro,acc)]
        else:
            acache.haccessor_to_workers[haccessor].append((macro,acc))
        macro.input_dict[pin.name] = accessor

        for pinname, pin in macro._pins.items():
            if pinname not in macro.input_dict:
                break
        else:
            self.update_macro_status(macro)

    def _find_cell_to_cell(self, cell_or_path, subpath):
        # Find to which other cells a cell or path connects
        # inefficient (linear-time) lookup, to be improved
        # Results are returned as accessors
        from .macro import Path
        if isinstance(cell_or_path, Path):
            cell = _cell
            if cell is None:
                return []
        else:
            cell = cell_or_path
        accessors = []
        for source_accessor, target_accessor in self.cell_to_cell:
            ok = False
            if isinstance(source_accessor, tuple):
                path, s_subpath = source_accessor
                assert isinstance(path, Path)
                if path._cell is cell and s_subpath == subpath:
                    accessor = self.get_default_accessor(cell)
                    accessor.subpath = subpath
                    ok = True
            else:
                if source_accessor.cell is cell:
                    if source_accessor.subpath == subpath:
                        ok = True
            if not ok:
                continue
            if isinstance(target_accessor, tuple):
                path, t_subpath = target_accessor
                assert isinstance(path, Path)
                if path._cell is None:
                    continue
                    target_accessor = self.get_default_accessor(path._cell)
                    target_accessor.subpath = t_subpath
            accessors.append(target_accessor)
        return accessors

    def _find_cell_from_cell(self, cell_or_path, subpath):
        # Find which other cell connects to a cell or path
        # inefficient (linear-time) lookup, to be improved
        # Result is returned as an accessor
        from .macro import Path
        if isinstance(cell_or_path, Path):
            if not cell_or_path._incoming:
                return None
            return cell_or_path._cell
        cell = cell_or_path
        for source_accessor, target_accessor in self.cell_to_cell:
            ok = False
            if isinstance(target_accessor, tuple):
                path, t_subpath = target_accessor
                assert isinstance(path, Path)
                if path._cell is cell and t_subpath == subpath:
                    target_accessor = self.get_default_accessor(cell)
                    target_accessor.subpath = subpath
                    ok = True
            elif target_accessor.cell is cell and target_accessor.subpath == subpath:
                ok = True
            if not ok:
                continue
            if isinstance(source_accessor, tuple):
                path, s_subpath = source_accessor
                assert isinstance(path, Path)
                if path._cell is None:
                    return None
                accessor = self.get_default_accessor(path._cell)
                accessor.subpath = s_subpath
                return accessor
            else:
                return source_accessor
        return None

    def _cell_upstream(self, cell, subpath, skip_path=None):
        # Returns the upstream dependency of a cell
        from .cell import Cell
        result = None
        while 1:
            if isinstance(cell, Cell):
                for path in cell._paths:
                    if path is skip_path:
                        continue
                    result0 = self._find_cell_from_cell(path, subpath)
                    if result0 is not None:
                        if result is not None:
                            warn("%s: multiple incoming bound paths have been bound; should not be possible!!" % cell)
                            break
                        result = result0
                if result is not None:
                    break
            result = self._find_cell_from_cell(cell, subpath)
            if result is not None:
                break
            result = self.cell_cache.cell_from_upstream.get(cell)
            if result is not None:
                result = result.get(subpath)
            break
        return result

    def _connect_cell_cell(self, source, target, source_subpath, target_subpath):
        from .macro import Path, create_path
        from .cell import Cell
        ispath_source, ispath_target = self._verify_connect(source, target)     
        current_upstream = self._cell_upstream(target, target_subpath)
        if current_upstream is not None:
            raise TypeError("Cell %s is already connected to %s" % (target, current_upstream))            

        connection = []
        accessors = []
        for cell, ispath_cell, subpath in \
          (source, ispath_source, source_subpath), (target, ispath_target, target_subpath):
            if isinstance(cell, Cell):
                if cell._celltype == "structured": 
                    raise TypeError
                accessor = self.get_default_accessor(cell)
                accessor.subpath = subpath
            else:
                assert isinstance(cell, Path)
                assert ispath_cell, (cell, ispath_cell)
                accessor = None
            if ispath_cell:
                path = create_path(cell)
                if cell is target:
                    assert not path._incoming, cell
                    path._incoming = True
                connect = (path, subpath)
            else:
                connect = accessor
            connection.append(connect)
            if accessor is not None:
                accessors.append(accessor)
        self.cell_to_cell.append(connection)
        if len(accessors) == 2:
            self.update_accessor_accessor(*accessors)

    def update_accessor_accessor(self, source, target):
        assert source.source_access_mode is None
        assert source.source_content_type is None
        assert target.source_access_mode is None
        assert target.source_content_type is None
        same = True
        if source.subpath is not None or target.subpath is not None:
            raise NotImplementedError ### cache branch; for source.subpath, get the value and apply subpath; for target.subpath, get the _monitor and set subpath
            same = False
        if source.cell._destroyed or target.cell._destroyed: return ### TODO, shouldn't happen...
        checksum = self.cell_cache.cell_to_buffer_checksums.get(source.cell) # TODO in case of cache tree depth
        """            
        for attr in ("celltype", "storage_type", "access_mode", "content_type"):
            if getattr(source, attr) != getattr(target, attr):
                same = False
        """
        for attr in ("storage_type", "access_mode"):
            if getattr(source, attr) != getattr(target, attr):
                same = False
        if same:
            if source.celltype != target.celltype:                
                print("Manager.py, line 1087: kludge for cson-plain types")
                assert source.celltype == "cson" and target.celltype == "plain"
                expression = source.to_expression(checksum)
                value = self.get_expression(expression)
                result = deserialize(
                    target.celltype, target.cell._subcelltype, target.cell.path,
                    value, from_buffer=False, buffer_checksum=None,
                    source_access_mode="plain", #bad
                    source_content_type="cson" #bad
                )
                target_buffer, target_checksum, target_obj, target_semantic_obj, target_semantic_checksum = result
                assert target.subpath is None
                self.set_cell(
                    target.cell, target_semantic_obj,
                    subpath = None,
                    from_buffer=False, 
                    origin=source.cell
                )
            else:
                self.set_cell_checksum(target.cell, checksum, self.status[source.cell][None])
        else:
            raise NotImplementedError ### cache branch

    def update_path_value(self, path):
        # Slow! needs to be improved (TODO)
        from .macro import Path
        assert path._cell is not None
        if path._cell._destroyed: return ### TODO, shouldn't happen...
        for source, target in self.cell_to_cell:
            if isinstance(source, tuple):
                spath, subpath = source
                assert isinstance(spath, Path)
                if spath != path:
                    continue
                source = self.get_default_accessor(path._cell)
                source.subpath = subpath
            if isinstance(target, tuple):
                tpath, subpath = target
                assert isinstance(tpath, Path)
                if tpath._cell is None:
                    continue
                if tpath._cell._destroyed: continue ### TODO, shouldn't happen...
                target = self.get_default_accessor(tpath._cell)                
                target.subpath = subpath
            self.update_accessor_accessor(source, target)

    def update_cell_to_cells(self, cell, data_status, auth_status, *, subpath, full, origin):
        # Slow! needs to be improved (TODO)
        from .macro import Path  
        for source, target in self.cell_to_cell:
            if isinstance(source, tuple):
                path, s_subpath = source
                assert isinstance(path, Path)
                if path._cell is not cell:
                    continue
                if s_subpath != subpath:
                    continue
                source = self.get_default_accessor(path._cell)
                source.subpath = s_subpath              
            else: #accessor
                if source.cell is not cell:
                    continue
                if source.subpath != subpath:
                    continue
            if isinstance(target, tuple):
                path, t_subpath = target
                assert isinstance(path, Path)
                tcell = path._cell
                if tcell is None:
                    continue
                target_accessor = self.get_default_accessor(tcell)
                target_accessor.subpath = t_subpath
            else:
                target_accessor = target
                tcell = target.cell
            assert tcell is not cell, (source, target, source.cell, cell)
            if full:                
                self.update_accessor_accessor(source, target_accessor)
            else:
                self._propagate_status(
                  tcell, data_status, auth_status, 
                  full=False, cell_subpath=subpath
                )

    def connect_cell(self, cell, other, cell_subpath):
        #print("connect_cell", cell, other)
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .worker import PinBase, EditPin
        from .macro import Path
        from .structured_cell import Inchannel
        if isinstance(cell, Link):
            cell = cell.get_linked()
        if not isinstance(cell, (Cell, Path)):
            raise TypeError(cell)
        if isinstance(other, Link):
            other = other.get_linked()

        other_subpath = None
        if isinstance(other, Inchannel):
            other_subpath = other.path
            other = other.structured_cell.cell        

        if isinstance(other, (Cell, Path)):
            self._connect_cell_cell(cell, other, cell_subpath, other_subpath)
        elif isinstance(other, PinBase):
            path_cell, path_other = self._verify_connect(cell, other)            
            if path_other:
                msg = str(other) + ": macro-generated pins/paths may not be connected outside the macro"
                raise Exception(msg)
            if path_cell:
                msg = str(cell) + ": macro-generated cells/paths may only be connected to cells, not %s"
                raise Exception(msg % other)                
            worker = other.worker_ref()
            if isinstance(worker, Transformer):
                self._connect_cell_transformer(cell, other, cell_subpath)
            elif isinstance(worker, Reactor):
                mode = "edit" if isinstance(other, EditPin) else "in"
                self._connect_reactor(other, cell, mode, cell_subpath)
            elif isinstance(worker, Macro):
                self._connect_cell_macro(cell, other, cell_subpath)
            else:
                raise TypeError(type(worker))
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
                    return accessor.cell, accessor.subpath
            elif isinstance(pin, EditPin):
                return rt_reactor.edit_dict.get(pin.name)
            elif isinstance(pin, OutputPin):
                return rt_reactor.output_dict.get(pin.name, [])
            else:
                raise TypeError(pin)
        elif isinstance(worker, Macro):
            accessor = worker.input_dict.get(pin, None)
            if accessor is None:
                return None
            else:
                return accessor.cell, accessor.subpath
        else:
            raise TypeError(worker)


    def connect_pin(self, pin, cell):
        #print("connect_pin", pin, cell)
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .macro import Path
        from .structured_cell import Inchannel
        from .worker import PinBase, InputPin, OutputPin, EditPin
        cell_subpath = None
        if isinstance(cell, Link):
            cell = cell.get_linked()
        cell_subpath = None
        if isinstance(cell, Inchannel):
            cell_subpath = cell.path
            cell = cell.structured_cell.cell
        if not isinstance(cell, (Cell, Path)):
            raise TypeError(cell)
        if not isinstance(pin, PinBase) or isinstance(pin, InputPin):
            raise TypeError(pin)

        path_pin, path_cell = self._verify_connect(pin, cell)
        if path_pin:
            msg = str(pin) + ": macro-generated pins may not be connected outside the macro"
            raise Exception(msg)

        worker = pin.worker_ref()
        if isinstance(worker, Transformer):
            tcache = self.transform_cache
            tcache.transformer_to_cells[worker].append((cell, cell_subpath))
            level1 = tcache.transformer_to_level1.get(worker)
            if level1 is not None:
                hlevel1 = level1.get_hash()
                checksum = tcache.get_result(hlevel1)
                if checksum is not None:
                    if cell_subpath is not None: raise NotImplementedError ###see update_accessor_accessor
                    self.set_cell_checksum(cell, checksum)
            self.update_transformer_status(worker,full=False, new_connection=True)
        elif isinstance(worker, Reactor):
            mode = "edit" if isinstance(pin, EditPin) else "out"
            self._connect_reactor(pin, cell, mode, cell_subpath)
        else:
            raise TypeError(worker)
        self.schedule_jobs()

    def _update_status(self, cell, defined, *, has_auth, origin, cell_subpath):
        status = self.status[cell][cell_subpath]
        old_data_status = status.data
        old_auth_status = status.auth        
        if not defined:
            status.data = "UNDEFINED"
        else:
            status.data = "OK"
        if not has_auth:
            status.auth = "OVERRULED"
        new_data_status = status.data if status.data != old_data_status else None
        new_auth_status = status.auth if status.auth != old_auth_status else None
        self._propagate_status(
            cell, new_data_status, new_auth_status, 
            full=True, origin=origin, cell_subpath=cell_subpath
        )
        self.schedule_jobs()

    @main_thread_buffered
    def set_cell_checksum(self, cell, checksum, status=None):
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell][None]
        has_auth = (auth != False)
        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        vcache = self.value_cache
        if checksum != old_checksum:
            ccache.cell_to_authority[cell][None] = True
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
            self._update_status(
                cell, (checksum is not None), 
                has_auth=has_auth, origin=None, cell_subpath=None
            )

    @main_thread_buffered
    def set_cell(self, cell, value, *, subpath,
      from_buffer=False, origin=None, buffer_checksum=None,
      ):
        # "origin" indicates the worker that generated the .set_cell call
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        assert buffer_checksum is None or from_buffer == True
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell][subpath]
        has_auth = (auth != False)     
        if subpath is not None: 
            raise NotImplementedError ### deep cells

        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        result = deserialize(
            cell._celltype, cell._subcelltype, cell.path,
            value, from_buffer=from_buffer, buffer_checksum=buffer_checksum,
            source_access_mode=None,
            source_content_type=None
        )
        buffer, checksum, obj, semantic_obj, semantic_checksum = result
        vcache = self.value_cache
        semantic_key = SemanticKey(
            semantic_checksum,
            cell._default_access_mode,
            None
        )
        if checksum != old_checksum:
            ccache.cell_to_authority[cell][subpath] = True
            ccache.cell_to_buffer_checksums[cell] = checksum
            if old_checksum is not None:
                vcache.decref(old_checksum, has_auth=has_auth)
            vcache.incref(checksum, buffer, has_auth=has_auth)
            vcache.add_semantic_key(semantic_key, semantic_obj)
            accessor = self.get_default_accessor(cell)
            accessor.subpath = subpath
            expression = accessor.to_expression(checksum)
            self.expression_cache.expression_to_semantic_key[expression.get_hash()] = semantic_key
            if subpath is None and not is_dummy_mount(cell._mount):
                if not get_macro_mode() and origin is not cell._context():
                    self.mountmanager.add_cell_update(cell)
            self._update_status(
              cell, (checksum is not None), 
              cell_subpath=subpath, has_auth=has_auth, origin=origin
            )
        else:
            # Just refresh the semantic key timeout
            vcache.add_semantic_key(semantic_key, semantic_obj)

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
    def set_cell_from_label(self, cell, label, subpath):
        if subpath is not None: raise NotImplementedError ###deep cells
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

    def _activate_context(self, ctx, value):
        from .context import Context
        from .reactor import Reactor
        from .macro import Macro
        from .transformer import Transformer
        def activate(child):
            if isinstance(child, Context):
                for cchild in child._children.values():
                    activate(cchild)
            elif isinstance(child, Macro):
                child._active = value
                cctx = child._gen_context
                if cctx is not None:
                    activate(cctx)
            elif isinstance(child, (Reactor, Transformer)):
                child._active = value
        activate(ctx)
    def deactivate_context(self, ctx):
        self._activate_context(ctx, False)                
    def activate_context(self, ctx):
        self._activate_context(ctx, True)                

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
                if delta is None:
                    await asyncio.gather(*cache_jobs)
                else:
                    await asyncio.wait(cache_jobs, timeout=delta)
                    continue
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
                tasks = list(self.cache_task_manager.tasks.values())
                if not len(tasks):
                    raise Exception("No jobs, but unstable workers: %s" % unstable)
                asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED, timeout=delta)
                continue
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

    def _destroy_cell(self, cell):
        ccache = self.cell_cache
        ccache.cell_to_accessors.pop(cell, None)
        ccache.cell_to_authority.pop(cell, None)
        ccache.cell_to_buffer_checksums.pop(cell, None)
        ccache.cell_from_upstream.pop(cell, None)

        for item in list(self.cell_to_cell):
            source, target = item
            destroy = False
            if isinstance(source, Accessor) and source.cell is cell:
                destroy = True
            if isinstance(target, Accessor) and target.cell is cell:
                destroy = True
            if destroy:
                self.cell_to_cell.remove(item)

    def _destroy_worker(self, worker):
        cache = self.accessor_cache.haccessor_to_workers        
        for k,v in cache.items():
            v[:] = [vv for vv in v if vv[0] is not worker]
    

    def _destroy_transformer(self, transformer):
        self._destroy_worker(transformer)
        tcache = self.transform_cache
        tcache.transformer_to_level0.pop(transformer)
        levels1 = []
        level1 = tcache.transformer_to_level1.pop(transformer, None)
        if level1 is not None:
            levels1.append(level1)
        levels1a = tcache.stream_transformer_to_levels1.pop(transformer, None)
        if levels1a is not None:
            levels1.extend(levels1a.values())
        for level1 in levels1:
            hlevel1 = level1.get_hash()
            tcache.decref(level1)
            tf = tcache.transformer_from_hlevel1.pop(hlevel1, None)
            if tf is not transformer:
                tcache.transformer_from_hlevel1[hlevel1] = tf
            else:
                # restore transformer_from_hlevel1 to an alternative tf
                #TODO: use reverse cache
                for tf, tf_level1 in tcache.transformer_to_level1.items():
                    if tf_level1.get_hash() == hlevel1:
                        tcache.transformer_from_hlevel1[hlevel1] = tf
                        break
        tcache.transformer_to_cells.pop(transformer, None)
        self.unstable.discard(transformer)

    def _destroy_macro(self, macro):        
        """destroys macro and its generated context
        NOTE: it is NOT necessary to destroy macro._paths or filter cell-cell connections
        Reasons:
        - Paths under macro control (i.e. non-global paths) are always expanded to cells first
          So from a manager perspective, they do not really exist
           and the cell is destroyed together with the macro.
        - Global paths do exist at a cell-cell connection level (and as upstreams)
          but they are never destroyed.
        - The third kind of paths is those constructed on the direction of verify_connect
          This involves connections into paths, whose target is controlled by a different macro.
          The other end of the connection MUST be under the control of the current macro;
           this is a requirement of verify_connect
          Therefore, the other end is also destroyed at the same time, and this will clean up
           the connection as well (self._destroy_cell).          
        """
        if macro._unbound_gen_context is not None:
            macro._unbound_gen_context.destroy()
        if macro._gen_context is not None:
            macro._gen_context.destroy()
        self._destroy_worker(macro)

    def _destroy_reactor(self, reactor):
        self._destroy_worker(macro)

    def destroy(self, from_del=False):
        if self._destroyed:
            return
        self._destroyed = True
        self.temprefmanager_future.cancel()
        self.flush_future.cancel()

    def __del__(self):
        self.destroy(from_del=True)

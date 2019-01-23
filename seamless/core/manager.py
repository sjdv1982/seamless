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
from .jobscheduler import JobScheduler
from .macro_mode import get_macro_mode, curr_macro

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
from enum import Enum
from collections import OrderedDict

def main_thread_buffered(func):
    def main_thread_buffered_wrapper(self, *args, **kwargs):
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(func, self, *args, **kwargs)
            self.workqueue.append(work)
        else:
            func(self, *args, **kwargs)
    return main_thread_buffered_wrapper



class Status:
    StatusDataEnum =  Enum('StatusDataEnum',
        ('OK', 'PENDING', 'UNDEFINED', 'UPSTREAM_ERROR', 'INVALID', 'UNCONNECTED')
    )
    # "UNCONNECTED" is only for workers
    # "INVALID" means parsing error or schema violation (with error message) (cell only)
    # "UPSTREAM_ERROR" means 'INVALID', 'UNDEFINED' or 'UNCONNECTED' upstream
    StatusExecEnum =  Enum('StatusExecEnum',
        ('FINISHED', 'EXECUTING', 'READY', 'PENDING', 'BLOCKED', 'ERROR')
    ) # "BLOCKED" means essentially "something in the data prevents me from running"
      # "ERROR" means an error in execution (with error message)
    StatusAuthEnum = Enum('StatusAuthEnum',
        ("FRESH", "PRELIMINARY", "OVERRULED", "OBSOLETE")
    )
    data_status = None  # in case of workers, the result of dependency propagation
    auth_status = None  # in case of workers, the result of dependency propagation
    exec_status = None  # only for workers: the result of execution
    _overruled = False
    def __init__(self, type):
        assert type in ("cell", "transformer", "macro", "reactor")
        self._type = type
        if type == "cell":
            self.data_status = self.StatusDataEnum.UNDEFINED
        else:
            self.data_status = self.StatusDataEnum.UNCONNECTED
            self.exec_status = self.StatusExecEnum.BLOCKED
        self.auth_status = self.StatusAuthEnum.FRESH

    def _str_cell(self):
        dstatus = self.data
        if dstatus == "UNDEFINED":
            return dstatus
        else:
            astatus = self.auth
            if astatus == "FRESH":
                return dstatus
            elif dstatus == "OK":
                return astatus
            else:
                return dstatus + "," + astatus

    def _str_transformer(self):
        dstatus = self.data
        estatus = self.exec
        if dstatus == "UNCONNECTED":
            return dstatus
        elif estatus == "BLOCKED":
            return self._str_cell()
        else:
            assert dstatus == "OK", (dstatus, estatus)
            astatus = self.auth
            if astatus == "FRESH":
                return estatus
            elif estatus == "FINISHED":
                return astatus
            else:
                return estatus + "," + astatus

    def _str_macro(self):
        return self._str_transformer()

    def _str_reactor(self):
        raise NotImplementedError ### cache branch

    def __str__(self):
        if self._type == "cell":
            return self._str_cell()
        elif self._type == "transformer":
            return self._str_transformer()
        elif self._type == "macro":
            return self._str_macro()
        elif self._type == "reactor":
            return self._str_reactor()
        else:
            raise TypeError(self._type)

    @property
    def data(self):
        return self.data_status.name

    @data.setter
    def data(self, value):
        v = getattr(self.StatusDataEnum, value.upper())
        self.data_status = v

    @property
    def exec(self):
        return self.exec_status.name

    @exec.setter
    def exec(self, value):
        v = getattr(self.StatusExecEnum, value.upper())
        self.exec_status = v

    @property
    def auth(self):
        return self.auth_status.name

    @auth.setter
    def auth(self, value):
        v = getattr(self.StatusAuthEnum, value.upper())
        self.auth_status = v

    def __eq__(self, other):
        return str(self) == str(other)

    def is_different(self, other):
        assert isinstance(other, Status)
        return (self.data_status != other.data_status) or \
            (self.exec_status != other.exec_status) or \
            (self.auth_status != other.auth_status)

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
        self.jobscheduler = JobScheduler(self)

        self.status = {}
        self.jobs = {}  # jobid-to-job
        self.executing = {}  # level2-transformer-to-jobid
        self.scheduled = []  # list of type-schedop-(add/remove) tuples
                             # type = "transformer", schedop = level1 transformer
                             # type = "macro", schedop = Macro object
                             # type = "reactor", schedop = (Reactor object, pin name, expression)
        self._temp_tf_level1 = {}
    
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
            key = type, hash(schedop)
            if key not in scheduled_clean:
                count = 0
            else:
                old_schedop, count = scheduled_clean[key][0]
                assert hash(old_schedop) == hash(schedop)
            dif = 1 if add_remove else -1
            scheduled_clean[key] = schedop, count + dif
        for key, value in scheduled_clean.items():
            type, _ = key
            schedop, count = value             
            
            if count == 0:
                continue
            if type == "transformer":
                tf_level1 = schedop
                hlevel1 = hash(tf_level1)
                if count > 0:
                    result = tcache.result_hlevel1.get(hash(tf_level1))
                    if result is not None:
                        self.set_transformer_result(tf_level1, None, None, result, False)
                        continue
                print("TODO: Manager.schedule_jobs(): try to launch a remote job")
                tf_level2 = tcache.build_level2(tf_level1)                 
                if count > 0:
                    result = tcache.result_hlevel2.get(hash(tf_level2))
                    if result is not None:
                        self.set_transformer_result(tf_level1, tf_level2, None, result, False)
                        continue
                    tcache.set_level2(tf_level1, tf_level2)
                self.jobscheduler.schedule(tf_level2, count)
            elif type == "macro":   
                raise NotImplementedError ### cache branch
            elif type == "reactor":   
                raise NotImplementedError ### cache branch
            else:
                raise ValueError(type)
        self.scheduled = []
        self._temp_tf_level1 = {}


    def set_transformer_result(self, level1, level2, value, checksum, prelim):
        print("SET-TRANSFORMER-RESULT", value)
        print("TODO: Manager.set_transformer_result: expand properly, see evaluate.py")
        assert value is not None
        tcache = self.transform_cache
        hlevel1 = hash(level1)        
        for tf, tf_level1 in tcache.transformer_to_level1.items(): #could be more efficient...
            if hash(tf_level1) != hlevel1:
                continue
            tstatus = self.status[tf]
            tstatus.exec = "FINISHED"
            tstatus.data = "OK"
            for cell in tcache.transformer_to_cells[tf]:
                status = self.status[cell]
                if prelim:                    
                    if status.auth == "FRESH":
                        status.auth = "PRELIMINARY"
                else:
                    if status.auth == "PRELIMINARY":
                        status.auth = "FRESH"
                self.set_cell(cell, value)
            self.update_transformer_status(tf)

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


    def get_expression(self, expression):
        if not isinstance(expression, Expression):
            raise TypeError(expression)
        semantic_key = self.expression_cache.expression_to_semantic_key.get(hash(expression))
        cache_hit = False
        if semantic_key is not None:
            value = self.value_cache.get_object(semantic_key)
            if value is not None:
                cache_hit = True
        if not cache_hit:
            checksum = expression.buffer_checksum
            buffer_item = self.value_cache.get_buffer(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            value = self.cache_expression(default_expression, buffer)
        return value

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
        self.status[cell] = Status("cell")

    def register_transformer(self, transformer):
        tcache = self.transform_cache
        tcache.transformer_to_level0[transformer] = {}
        tcache.transformer_to_cells[transformer] = []
        self.status[transformer] = Status("transformer")

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

    def _propagate_status(self, cell, data_status, auth_status):
        if cell._celltype == "structured": raise NotImplementedError ### cache branch
        status = self.status[cell]
        new_data_status = status.data  
        new_auth_status = status.auth      
        if data_status is not None:
            dstatus = status.data
            if data_status == "PENDING":
                if dstatus == "UPSTREAM_ERROR":
                    new_data_status = "PENDING"
            if data_status == "UPSTREAM_ERROR":
                if dstatus == "PENDING":
                    new_data_status = "UPSTREAM_ERROR"        
        if auth_status is not None:
            new_auth_status = auth_status

        if new_auth_status is not None or new_data_status is not None:
            for accessor in self.cell_cache.cell_to_accessors[cell]:
                for target_cell in self.accessor_cache.accessor_to_cells[accessor]:
                    self._propagate_status(
                      target_cell, new_data_status, new_auth_status
                    )
                for worker in self.accessor_cache.accessor_to_workers[accessor]:                    
                    self.update_worker_status(worker)

    def update_transformer_status(self, transformer):
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        old_status = self.status[transformer]
        new_status = Status("transformer")
        new_status.data, new_status.exec, new_status.auth = "OK", "READY", "FRESH"
        if old_status is not None and old_status.exec == "FINISHED":
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
            if len(target_cells) and new_status.auth == "FRESH":
                scheduled = self._schedule_transformer(transformer)
                if not scheduled:
                    propagate_data = False
        elif new_status.exec == "BLOCKED":
            if transformer in self.unstable:
                self.unstable.remove(transformer)
            if old_status.exec != "BLOCKED":
                self._unschedule_transformer(transformer)
        if propagate_data or propagate_auth:
            print("UPDATE", transformer, old_status, "=>", new_status)
            data_status = new_status.data if propagate_data else None
            auth_status = new_status.auth if propagate_auth else None
            for cell in target_cells:
                self._propagate_status(cell, data_status, auth_status)

    def update_worker_status(self, worker):
        from . import Transformer, Reactor, Macro
        if isinstance(worker, Transformer):
            return self.update_transformer_status(worker)
        else:
            raise NotImplementedError ### cache branch

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
        acache = self.accessor_cache
        if accessor not in acache.accessor_to_workers:
            acache.accessor_to_workers[accessor] = [transformer]
        else:
            acache.accessor_to_workers[accessor].append(transformer)
        accessor_dict[pin.name] = accessor
        self.update_transformer_status(transformer)

        if io == "input":
            pass
        elif io == "edit":
            raise NotImplementedError ### cache branch
        elif io == "output":
            raise TypeError(io) #outputpin, cannot connect a cell to that...
        else:
            raise TypeError(io)

    def connect_cell(self, cell, other):
        from . import Transformer, Reactor, Macro
        from .cell import Cell
        from .worker import PinBase
        if not isinstance(cell, Cell):
            raise TypeError(cell)
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
        self.schedule_jobs()

    def connect_pin(self, pin, cell):
        from . import Transformer, Reactor, Macro
        from .cell import Cell
        from .worker import PinBase, InputPin, OutputPin, EditPin
        if not isinstance(cell, Cell):
            raise TypeError(cell)
        if not isinstance(pin, PinBase) or isinstance(pin, InputPin):
            raise TypeError(pin)
        if isinstance(pin, EditPin):
            raise NotImplementedError ###cache branch

        worker = pin.worker_ref()
        if isinstance(worker, Transformer):
            self.transform_cache.transformer_to_cells[worker].append(cell)
            self.update_transformer_status(worker)            
        elif isinstance(worker, Macro):
            raise NotImplementedError ###cache branch
        elif isinstance(worker, Reactor):
            raise NotImplementedError ###cache branch
        else:
            raise TypeError(worker)
        self.schedule_jobs()

    def _update_status(self, cell, checksum, *, has_auth):
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
        if new_auth_status is not None or new_data_status is not None:
            self._propagate_status(cell, new_data_status, new_auth_status)
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
            self._update_status(cell, checksum, has_auth=has_auth)

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
            self._update_status(cell, checksum, has_auth=has_auth)
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
        self.schedule_jobs()

    async def equilibrate(self, timeout, report):
        delta = None
        if timeout is not None:
            deadline = time.time() + timeout
        while 1:
            if not len(self.unstable):
                break
            if timeout is not None:
                remain = deadline - time.time()
                if remain <= 0:
                    break
                if delta is not None and remain < delta:
                    delta = remain
            if report is not None:
                if delta is not None and report < delta:
                    delta = report
            if delta is None:
                jobs = []
                for job in itertools.chain(
                    self.jobscheduler.jobs.values(),
                    self.jobscheduler.remote_jobs.values(),
                  ):
                    if job.coroutine is not None:
                        jobs.append(job.coroutine)
                await asyncio.gather(*jobs)
            else:
                await asyncio.sleep(delta)
        return self.unstable
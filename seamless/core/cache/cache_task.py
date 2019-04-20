"""Asynchronous tasks involving (mostly remote) cache accesses
These tasks interrogate caches and either generate a result, or schedule a transform job
The result itself will be discarded, but a resultfunc can be defined that will be 
 triggered upon task completion, and which may write the result into cache.
Every key will always have the same CacheTask
    key = ("transform", "all", level1) => manager._schedule_transform_all(level1, count)
    key = ("transform", "job", level1) => manager._schedule_transform_job(level1, count)
    key = ("label", checksum) => remote label cache (label-to-checksum)
    key = ("value", checksum) => remote value cache (value-to-checksum)
    key = ("transformer_result", checksum) => remote transformer result cache
    key = ("transformer_result_level2", checksum) => remote level 2 transformer result cache
"""

import asyncio
import atexit
import inspect
from ..run_multi_remote import run_multi_remote, run_multi_remote_pair

remote_transformer_result_servers = []
remote_transformer_result_level2_servers = []
remote_checksum_from_label_servers = []
remote_checksum_value_servers = []

class CacheTask:
    """Wrapper around an async future of which the result will be discarded"""
    def __init__(self,key,future,count,resultfunc, cancelfunc):
        if not isinstance(future, (asyncio.Future, asyncio.Task)):
            raise TypeError(future)
        self.future = future
        self.key = key
        self.count = count
        self.resultfunc = resultfunc
        self.cancelfunc = cancelfunc
        if resultfunc is not None:
            future.add_done_callback(resultfunc)
        future.add_done_callback(cancelfunc)
    
    def incref(self, count=1):
        assert count > 0
        self.count += count

    def decref(self, count=1):
        count = abs(count)
        self.count -= count
        if self.count <= 0:
            self.cancel()            

    def cancel(self):
        future = self.future
        if not future.cancelled() and not future.done():
            future.cancel()

    def join(self):
        asyncio.get_event_loop().run_until_complete(self.future)

class CacheTaskManager:
    def __init__(self):
        self.tasks = {}

    def schedule_task(self, key, func, count, *, resultfunc=None, cancelfunc=None):
        assert count != 0
        if count > 0:
            if key not in self.tasks:
                future = asyncio.ensure_future(func)
                def cancelfunc2(f):
                    task = self.tasks.pop(key)
                    if future.cancelled():                                         
                        if cancelfunc is not None:
                            cancelfunc()
                    elif task.future.done():
                        exc = task.future.exception()
                        if exc is not None:
                            raise exc
                    else:
                        task.cancel()
                        if cancelfunc is not None:
                            cancelfunc()
                task = CacheTask(key, future, count, resultfunc, cancelfunc2)
                self.tasks[key] = task
            else:
                task = self.tasks[key]
                if inspect.iscoroutine(func):
                    asyncio.Task(func).cancel()
                task.incref(count)            
        else:
            task = self.tasks.get(key)
            if task is not None:
                task.decref(count)            
        return task
    
    def remote_checksum_from_label(self, label, origin=None):
        future = run_multi_remote(remote_checksum_from_label_servers, label, origin)
        if future is None:
            return None                    
        key = ("label", label)
        def resultfunc(future):
            checksum = future.result()
            if checksum is not None:
                for label_cache in label_caches:
                    label_cache.set(label, checksum)
        return self.schedule_task(key, future, 1, resultfunc=resultfunc)

    def remote_value(self, checksum, origin=None):
        #from ..manager import mixed_deserialize
        future = run_multi_remote_pair(remote_checksum_value_servers, checksum, origin)
        if future is None:
            return None                    
        key = ("value", checksum)
        def resultfunc(future):
            result = future.result()
            if result is not None:
                buffer = result
                for value_cache in value_caches:
                    value_cache.incref(checksum, buffer, has_auth=False)
        return self.schedule_task(key, future, 1, resultfunc=resultfunc)

    def remote_transform_result(self, hlevel1, origin=None):
        future = run_multi_remote(remote_transformer_result_servers, hlevel1, origin)
        if future is None:
            return None
        key = ("transformer_result", hlevel1)
        return self.schedule_task(key, future, 1)

    def remote_transform_result_level2(self, hlevel2, origin=None):
        future = run_multi_remote(remote_transformer_result_level2_servers, hlevel2, origin)
        if future is None:
            return None
        key = ("transformer_result_level2", hlevel2)
        return self.schedule_task(key, future, 1)

    def destroy(self):
        tasks = list(self.tasks.values())
        self.tasks.clear()
        for task in tasks:
            task.cancel()
            

from .transform_cache import transform_caches
from .label_cache import label_caches
from .value_cache import value_caches

cache_task_manager = CacheTaskManager()
atexit.register(cache_task_manager.destroy)
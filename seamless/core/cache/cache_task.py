"""Asynchronous tasks involving local and remote cache accesses
Every key will always have the same CacheTask
    key = ("transform", "all", level1) => manager._schedule_job(level1, count)
    key = ("transform", level1) => remote transformer result cache

"""

import asyncio
from ..run_multi_remote import run_multi_remote

remote_transformer_result_servers = []
remote_checksum_from_label_servers = []

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
        if not future.cancelled():
            future.cancel()
            self.cancelfunc()

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
                def cancelfunc2(future): 
                    self.tasks.pop(key)
                    if cancelfunc is not None:
                        cancelfunc()
                task = CacheTask(key, future, count, resultfunc, cancelfunc2)
                self.tasks[key] = task
            else:
                task = self.tasks[key]
                task.incref(count)            
        else:
            task = self.tasks[key]
            task.decref(count)            
        return task
    
    def remote_checksum_from_label(self, label):
        future = run_multi_remote(remote_checksum_from_label_servers, label)
        if future is None:
            return None                    
        key = ("checksum_from_label", label)
        def resultfunc(future):
            checksum = future.result()
            for label_cache in label_caches:
                label_cache.set(label, checksum)
        return self.schedule_task(key, future, 1, resultfunc=resultfunc)

    def remote_value(self, checksum):
        raise NotImplementedError  ### cache branch

    def remote_transform_result(self, hlevel1):
        future = run_multi_remote(remote_transformer_result_servers, hlevel1)
        if future is None:
            return None
        key = ("transform_result", hlevel1)
        def resultfunc(future):
            checksum = future.result()
            for transform_cache in transform_caches:
                transform_cache.result_hlevel1[hlevel1] = checksum
        return self.schedule_task(key, future, 1, resultfunc=resultfunc)

from .transform_cache import transform_caches
from .label_cache import label_caches

cache_task_manager = CacheTaskManager()
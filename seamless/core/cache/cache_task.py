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
    def __init__(self,key,future,count,callback):
        if not isinstance(future, (asyncio.Future, asyncio.Task)):
            raise TypeError(future)
        self.future = future
        self.key = key
        self.count = count
        self.callback = callback
        future.add_done_callback(callback)
    
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
            self.callback()

    def join(self):
        asyncio.get_event_loop().run_until_finished(self.future)

class CacheTaskManager:
    def __init__(self):
        self.tasks = {}

    def schedule_task(self, key, func, count, cancelfunc=None):
        assert count != 0
        if count > 0:
            if key not in self.tasks:
                future = asyncio.ensure_future(func)
                def cancel(future): 
                    self.tasks.pop(key)
                    if cancelfunc is not None:
                        cancelfunc()
                task = CacheTask(key, future, count, cancel)
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
        return self.schedule_task(key, future, 1)

    def remote_value(self, checksum):
        raise NotImplementedError  ### cache branch

    def remote_transform_result(self, level1):                
        future = run_multi_remote(remote_transformer_result_servers, level1)
        if future is None:
            return None
        key = ("transform", level1)
        return self.schedule_task(key, future, 1)
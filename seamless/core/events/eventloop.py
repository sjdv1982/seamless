from collections import deque
import time
import weakref
import threading
import traceback
import asyncio


# TODO: eventloop flush that waits until a particular event (sync or async or singleton) has finished.
# such a flush comes in two flavors, sync and async.
# the sync one runs in a thread

class EventLoop:
    def __init__(self, manager):
        self.deque = deque()
        self._flushing = False
        self.manager = weakref.ref(manager)
        print("TODO: integrate eventloop with jobscheduler, cache_task_manager")
        """        
        self.jobscheduler = JobScheduler(self)
        self.cache_task_manager = cache_task_manager
        """

    def append(self, event):
        from . import Event
        assert isinstance(event, Event)
        self.deque.append(event)

    async def flush(self, timeout=None):
        assert threading.current_thread() is threading.main_thread()
        manager = self.manager()
        if timeout is not None:
            timeout_time = time.time() + timeout/1000        
        self._flushing = True
        while len(self.deque):
            if timeout is not None:
                if time.time() > timeout_time:
                    break
            if manager._destroyed or not manager._active:
                break
            try:
                event.process(manager)
            except Exception:
                traceback.print_exc()
            yield
        self._flushing = False

    def __len__(self):
        return len(self.deque)


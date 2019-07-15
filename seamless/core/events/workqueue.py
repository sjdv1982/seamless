import time
from collections import deque
import threading
import traceback
import asyncio

class WorkQueue:
    _ipython_registered = False
    def __init__(self, manager):
        self.deque = deque()
        self._priority_work = deque()
        self._flushing = False
        self._append_lock = threading.Lock()
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
        manager = self.
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


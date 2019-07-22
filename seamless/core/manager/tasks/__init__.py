import weakref
import asyncio
from asyncio import CancelledError

class Task:    
    def __init__(self, manager):        
        if isinstance(manager, weakref.ref):
            manager = manager()
        assert isinstance(manager, Manager)
        self.manager = weakref.ref(manager)        
        self.future = None
        self.dependencies = []

    async def run(self):
        self._launch()
        try:
            await self.future
        except CancelledError:
            if self.future is not None:
                self.future.cancel()
        return self.future.result()
    
    def _launch(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        awaitable = self._run(manager)
        self.future = asyncio.ensure_future(awaitable)
        raise NotImplementedError
        taskmanager.add_task(self) # also clean-up the task when done or cancelled!
        return taskmanager

    def launch(self):
        self._launch()

    def launch_and_await(self):
        # Blocking version of launch
        taskmanager = self._launch()
        taskmanager.loop.run_until_complete(self.future)

    def cancel(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            if self.future is not None:
                self.future.cancel()
            return
        taskmanager = manager.taskmanager
        taskmanager.cancel_task(self)


from .. import Manager
from .setvalue import SetCellValueTask
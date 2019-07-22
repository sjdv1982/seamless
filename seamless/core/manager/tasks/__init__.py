import weakref
import asyncio
from asyncio import CancelledError
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
# TODO: custom ProcessPool executor that plays nice with local transformations
process_pool = ProcessPoolExecutor()
thread_pool = ThreadPoolExecutor()


class Task:
    _executor = None
    _realtask = None
    
    def __init__(self, manager, *args, **kwargs):        
        if isinstance(manager, weakref.ref):
            manager = manager()        
        assert isinstance(manager, Manager)
        if self.refkey is not None:
            taskmanager = manager.taskmanager
            reftask = taskmanager.reftasks.get(refkey)
            if reftask is not None:
                self.set_realtask(reftask)
                return
            else:
                taskmanager.reftasks[refkey] = self
                taskmanager.rev_reftasks[self] = refkey
        self.manager = weakref.ref(manager)        
        self.future = None
        self.dependencies = []
        self.refholders = [self] # tasks that are value-identical to this one, 
                                # of which this one is the realtask

    @property
    def refkey(self):
        return None

    def set_realtask(self, realtask):
        self._realtask = realtask
        realtask.refholders.append(self)

    async def run(self):
        realtask = self._realtask
        if realtask is not None:
            return realtask.run()
        self._launch()
        try:
            await asyncio.shield(self.future)
        except CancelledError:
            self.cancel()
        return self.future.result()
    
    def _launch(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        if self.future is not None:
            return taskmanager        
        if self._executor is None:
            awaitable = self._run(manager)
        else:
            loop = taskmanager.loop
            with self._executor as executor:
                awaitable = loop.run_in_executor(
                    executor,
                    self._run,
                    manager
                )        
        self.future = asyncio.ensure_future(awaitable)
        taskmanager.add_task(self)
        return taskmanager

    def launch(self):
        realtask = self._realtask
        if realtask is not None:
            return realtask.launch()
        self._launch()

    def launch_and_await(self):
        realtask = self._realtask
        if realtask is not None:
            return realtask.launch_and_await()
        # Blocking version of launch
        taskmanager = self._launch()
        taskmanager.loop.run_until_complete(self.future)

    def cancel_refholder(self, refholder):
        assert self._realtask is None
        self.refholders.remove(refholder)
        if not len(self.refholders):            
            self.cancel()

    def cancel(self):
        realtask = self._realtask
        if realtask is not None:
            return realtask.cancel_refholder(self)
        manager = self.manager()
        if self.future is not None:
            if self.future.cancelled():
                return
            self.future.cancel()        
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        taskmanager.cancel_task(self)


from .set_value import SetCellValueTask
from .serialize_buffer import SerializeBufferTask
#from .calculate_checksum import CalculateChecksumTask
from ..manager import Manager

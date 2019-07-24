import weakref
import asyncio
from asyncio import CancelledError


class Task:
    _realtask = None
    _awaiting = False
    future = None
    
    def __init__(self, manager, *args, **kwargs):        
        if isinstance(manager, weakref.ref):
            manager = manager()        
        assert isinstance(manager, Manager)
        self._dependencies = []
        if self.refkey is not None:
            taskmanager = manager.taskmanager
            reftask = taskmanager.reftasks.get(self.refkey)
            if reftask is not None:
                self.set_realtask(reftask)
                return
            else:
                taskmanager.reftasks[self.refkey] = self
                taskmanager.rev_reftasks[self] = self.refkey
        self.manager = weakref.ref(manager)                
        self.refholders = [self] # tasks that are value-identical to this one, 
                                # of which this one is the realtask

    @property
    def refkey(self):
        return None

    @property
    def dependencies(self):
        if self._realtask is not None:
            return self._realtask.dependencies
        else:
            return self._dependencies

    def set_realtask(self, realtask):
        self._realtask = realtask
        realtask.refholders.append(self)

    async def run(self):
        #if self.future is not None:
        #    print("RUN", self)
        realtask = self._realtask
        if realtask is not None:
            result = await realtask.run()
            return result
        self._launch()
        self._awaiting = True
        #print("LAUNCHED", self)
        #if self.__class__.__name__ != "CellChecksumTask": await asyncio.sleep(2) ###
        try:
            await asyncio.shield(self.future)
        except CancelledError:                        
            self.cancel()
            raise
        #print("HAS RUN", self)
        return self.future.result()
    
    def _launch(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        if self.future is not None:
            return taskmanager
        #print("LAUNCH", self)     
        awaitable = self._run()
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
        self._awaiting = True
        taskmanager.loop.run_until_complete(self.future)
        return self.future.result()

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
from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .checksum import CellChecksumTask, CalculateChecksumTask
from .cell_update import CellUpdateTask
from .get_buffer import GetBufferTask
from .upon_connection import UponConnectionTask
from ..manager import Manager

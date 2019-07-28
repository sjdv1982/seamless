from . import Task

class WorkerUpdateTask(Task):
    def __init__(self, manager, worker):
        raise NotImplementedError #livegraph branch
        #assert isinstance(accessor, ReadAccessor)        
        #self.accessor = accessor
        #super().__init__(manager)
        #self.dependencies.append(accessor)

    async def _run(self):
        raise NotImplementedError #livegraph branch
        #accessor = self.accessor

from . import Task
import traceback
import copy

print("TODO: tasks/structured_cell.py: task to deserialize editchannel, then structured_cell.set_auth_path")

class StructuredCellJoinTask(Task):    
    def __init__(self, manager, structured_cell):
        super().__init__(manager)
        self.structured_cell = structured_cell
        self.dependencies.append(structured_cell)

    async def await_sc_tasks(self):
        sc = self.structured_cell
        manager = self.manager()
        taskmanager = manager.taskmanager
        tasks = []
        for task in taskmanager.tasks:
            if sc not in task.dependencies:
                continue
            if task.taskid >= self.taskid or task.future is None:
                continue
            tasks.append(task)
        if len(tasks):
            await taskmanager.await_tasks(tasks, shield=True)


    async def _run(self):
        manager = self.manager()
        sc = self.structured_cell
        await self.await_sc_tasks()
        if len(sc.inchannels):
            raise NotImplementedError # livegraph branch
            # ...
            """
            Most challenging part is to put this in a Backend that:
            - Supports hash patterns
            - Computes values on demand, coming from validator code)        
            - Computes form and storage on demand, coming from form validation rules
            Fortunately, ***mixed buffers store form and storage!!!***
            Also, Backend can be read-only!
            """
            # checksum = ...
        else:
            value = sc._auth_value            
        buf = await SerializeToBufferTask(
            manager, value, "mixed", use_cache=False # the value object changes all the time...
        ).run()
        checksum = await CalculateChecksumTask(manager, buf).run()
        if checksum is not None:
            checksum = checksum.hex()        
        if not len(sc.inchannels):
            sc.auth._set_checksum(checksum, from_structured_cell=True)
        if sc.buffer is not sc.auth:            
            sc.buffer._set_checksum(checksum, from_structured_cell=True)
        if sc.schema is not None:
            if len(sc.inchannels):
                raise NotImplementedError # livegraph branch  # see above
            schema = sc.schema.value
            if schema is not None:
                s = Silk(data=copy.deepcopy(value), schema=schema)
                try:
                    s.validate()
                except ValidationError:
                    traceback.print_exc()
        
        if sc._data is not sc.buffer:
            sc._data._set_checksum(checksum, from_structured_cell=True)
        if sc.outchannels:
            raise NotImplementedError # livegraph branch
        sc.modified_auth_paths.clear()

from .serialize_buffer import SerializeToBufferTask
from .checksum import CalculateChecksumTask
from ....silk.Silk import Silk, ValidationError
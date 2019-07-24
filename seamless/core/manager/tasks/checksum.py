from . import Task
from ...protocol import calculate_checksum

class CalculateChecksumTask(Task):
    @property
    def refkey(self):
        return id(self.buffer)

    def __init__(self, manager, buffer): 
        self.buffer = buffer
        super().__init__(manager)      

    async def _run(self):
        manager = self.manager()
        result = await calculate_checksum(self.buffer)
        return result 


class CellChecksumTask(Task):

    def __init__(self, manager, cell): 
        self.cell = cell
        super().__init__(manager)
        self.dependencies.append(cell)

    async def _run(self):
        """Updates the checksum of the cell.
- Await all UponConnectionTasks
- Await current set-path/set-auth-path tasks for the cell. It doesn't matter if they were cancelled.  
- Await get buffer task
- Await calculate checksum task
- If the checksum is not None and cell's void attribute is True, log a warning, set it to False, and launch a cell update task
- Set the cell's checksum attribute (direct attribute access)
- If the checksum was None but the void attribute was not None, do a cell void cancellation.
        """
        from . import SerializeToBufferTask

        manager = self.manager()
        await manager.taskmanager.await_upon_connection_tasks()
        cell = self.cell

        if cell._monitor:
            # - Await current set-path/set-auth-path tasks for the cell. It doesn't matter if they were cancelled.  
            raise NotImplementedError # livegraph branch
        else:
            taskmanager = manager.taskmanager
            if cell in taskmanager.cell_to_value:
                celltype = cell._celltype
                value = taskmanager.cell_to_value[cell]
                if value is None:
                    checksum = None
                else:
                    buffer = await SerializeToBufferTask(manager, value, celltype).run()
                    checksum = await CalculateChecksumTask(manager, buffer).run()
            else:
                checksum = cell._checksum            
        void = cell._void
        manager._set_cell_checksum(cell, checksum, checksum is None)
        if void and checksum is None:
            manager.cancel_cell(cell, void=True, origin_task=self)
        return None
        
        

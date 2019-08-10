import asyncio
from . import Task
from ...protocol.calculate_checksum import calculate_checksum

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

    def __init__(self, manager, cell, awaiting_task = None): 
        self.cell = cell
        super().__init__(manager)
        self.awaiting_task = awaiting_task
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
        from .serialize_buffer import SerializeToBufferTask
        from .set_value import SetCellValueTask
        from .set_buffer import SetCellBufferTask
        from .cell_update import CellUpdateTask

        manager = self.manager()
        await manager.taskmanager.await_upon_connection_tasks(self.taskid)
        cell = self.cell
        invalid = False
        checksum = None

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
                    try:
                        buffer = await SerializeToBufferTask(manager, value, celltype).run()
                        checksum = await CalculateChecksumTask(manager, buffer).run()
                    except Exception:
                        invalid = True
            else:
                taskid = self.taskid
                awaiting_task = self.awaiting_task
                while 1:
                    for task in taskmanager.tasks:
                        if task.taskid >= taskid:
                            continue
                        if task is awaiting_task:
                            continue
                        if isinstance(task, (SetCellValueTask, SetCellBufferTask)):
                            continue
                        if cell in task.dependencies:
                            break                        
                    else:
                        break
                    await asyncio.sleep(0)
                checksum = cell._checksum   
                if checksum is None:
                    return         
        old_void = cell._void
        void = (checksum is None)
        old_status_reason = cell._status_reason
        if void:
            if invalid:
                status_reason = StatusReasonEnum.INVALID
            elif manager.livegraph.has_authority(cell):
                status_reason = StatusReasonEnum.UNDEFINED
            else:
                status_reason = StatusReasonEnum.UPSTREAM        
            if not old_void or status_reason != old_status_reason:
                manager.cancel_cell(
                    cell, 
                    void=True, 
                    origin_task=self,
                    reason=status_reason
                )
        return None
        
from ...status import StatusReasonEnum        

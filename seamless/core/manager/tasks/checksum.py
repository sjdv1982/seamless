from . import Task, process_pool
from ...protocol import calculate_checksum

class CalculateChecksumTask(Task):
    _executor = process_pool

    @property
    def refkey(self):
        return id(self.buffer)

    def __init__(self, manager, buffer): 
        super.__init__(manager)      
        if self._realtask is not None:
            return
        self.buffer = buffer

    def _run(self): # not async, since we run in ProcessPoolExecutor
        return calculate_checksum(self.buffer)


class CellChecksumTask(Task):

    def __init__(self, manager, cell): 
        super.__init__(manager)
        self.cell = cell
        self.dependencies = [cell]

    async def _run(self):
        """Updates the checksum of the cell.
- Await current set-path/set-auth-path tasks for the cell. It doesn't matter if they were cancelled.  
- Await get buffer task
- Await calculate checksum task
- If the checksum is not None and cell's void attribute is True, log a warning, set it to False, and launch a cell update task
- Set the cell's checksum attribute (direct attribute access)
- If the checksum was None but the void attribute was not None, do a cell void cancellation.
        """
        from . import GetBufferTask
        if cell._monitor:
            # - Await current set-path/set-auth-path tasks for the cell. It doesn't matter if they were cancelled.  
            raise NotImplementedError # livegraph branch
        manager = self.manager
        cell = self.cell
        buffer = await GetBufferTask(manager, cell).run()
        checksum = await CalculateChecksumTask(manager, buffer).run()
        void = cell._void
        manager._set_cell_checksum(self, cell, checksum, checksum is None)
        if void and checksum is None:
            manager.cancel_cell(void=True)
        
        

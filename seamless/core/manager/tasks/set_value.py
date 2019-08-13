from . import Task

class SetCellValueTask(Task):
    # For values that come from the command line
    def __init__(self, manager, cell, value):
        super().__init__(manager)
        self.cell = cell
        self.value = value        
        self.dependencies.append(cell)

    async def _run(self):
        from . import SerializeToBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid)
        cell = self.cell
        try:
            taskmanager.cell_to_value[cell] = self.value
            buffer = await SerializeToBufferTask(manager, self.value, cell._celltype).run()
            checksum = await CalculateChecksumTask(manager, buffer,).run()
            if checksum is not None:
                buffer_cache = manager.cachemanager.buffer_cache
                await validate_subcelltype(
                    checksum, cell._celltype, cell._subcelltype, 
                    str(cell), buffer_cache
                )
                checksum_cache[checksum] = buffer
                buffer_cache.incref(checksum)
                manager._set_cell_checksum(self.cell, checksum, False)
                CellUpdateTask(manager, self.cell).launch()
        finally:
            taskmanager.cell_to_value.pop(cell, None)
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.calculate_checksum import checksum_cache

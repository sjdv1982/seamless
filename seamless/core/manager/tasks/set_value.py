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
        await taskmanager.await_upon_connection_tasks()
        cell = self.cell
        try:
            taskmanager.cell_to_value[cell] = self.value
            buffer = await SerializeToBufferTask(manager, self.value, cell._celltype).run()
            checksum = await CalculateChecksumTask(manager, buffer).run()
            if checksum is None:
                manager.cancel_cell(cell)
            else:
                value_cache = manager.cachemanager.value_cache
                await validate_subcelltype(
                    checksum, cell._celltype, cell._subcelltype, value_cache
                )
                if cell._checksum != checksum:
                    manager._set_cell_checksum(cell, checksum, checksum is None)
                    CellUpdateTask(manager, self.cell).launch()
        finally:
            taskmanager.cell_to_value.pop(cell)
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
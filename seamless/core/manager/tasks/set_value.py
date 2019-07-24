from . import Task

class SetCellValueTask(Task):
    def __init__(self, manager, cell, value):
        super().__init__(manager)
        self.cell = cell
        self.value = value
        self.dependencies.append(cell)

    async def _run(self):
        from . import SerializeToBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        taskmanager = manager.taskmanager
        cell = self.cell
        try:
            taskmanager.cell_to_value[cell] = self.value
            buffer = await SerializeToBufferTask(manager, self.value, cell._celltype).run()
            checksum = await CalculateChecksumTask(manager, buffer).run()
            manager._set_cell_checksum(cell, checksum, checksum is None)
            CellUpdateTask(manager, self.cell).launch()
        finally:
            taskmanager.cell_to_value.pop(cell)
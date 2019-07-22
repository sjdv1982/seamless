from . import Task

class SetCellValueTask(Task):
    def __init__(self, manager, cell, value):
        super().__init__(manager)
        self.cell = cell
        self.value = value
        self.dependencies.append(cell)

    async def _run(self):
        from . import SerializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        cell = self.cell
        buffer = await SerializeBufferTask(manager, self.value, cell._celltype).run()
        checksum = await CalculateChecksumTask(manager, buffer).run()
        manager._set_cell_checksum(self, cell, checksum, checksum is None)
        CellUpdateTask(manager, self.cell).launch()
        
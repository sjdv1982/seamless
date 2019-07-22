from . import Task

class SetCellValueTask(Task):
    def init(self, manager, cell, value):
        self.cell = cell
        self.value = value
        self.dependencies.append(cell)

    async def _run(self, manager):
        from . import SerializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager
        buffer = await SerializeBufferTask(manager, self.value, cell.celltype).run()
        checksum = await CalculateChecksumTask(manager, buffer).run()
        CellUpdateTask(manager, self.cell).launch()
        
from . import Task

class SetCellValueTask(Task):
    def __init__(self, manager, cell, value):
        super().__init__(manager)
        self.cell = cell
        self.value = value
    async def _run(self, manager):
        from .. import SerializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager
        await buffer = SerializeBufferTask(manager, self.value, cell.celltype).run()
        await checksum = CalculateChecksumTask(manager, buffer).run()
        CellUpdateTask(manager, self.cell).launch()
        
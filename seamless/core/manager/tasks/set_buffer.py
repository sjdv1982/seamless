from . import Task

text_types = (
    "text", "python", "ipython", "cson", "yaml",
    "str", "int", "float", "bool",
)

class SetCellBufferTask(Task):
    # For buffers that come from the command line
    def __init__(self, manager, cell, buffer, checksum):
        super().__init__(manager)
        self.cell = cell
        self.buffer = buffer      
        self.checksum = checksum
        self.dependencies.append(cell)

    async def _run(self):
        from . import DeserializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        taskmanager = manager.taskmanager
        await taskmanager.await_upon_connection_tasks(self.taskid)
        cell = self.cell
        buffer = self.buffer
        checksum = self.checksum        
        if (checksum is None and buffer is not None) or \
            (checksum, cell._celltype) not in evaluation_cache_1:
                if cell._celltype in text_types:
                    assert buffer.endswith(b"\n")
                await DeserializeBufferTask(
                    manager, buffer,
                    self.checksum, cell._celltype, copy=False
                ).run()
        if checksum is None and buffer is not None:
            checksum = await CalculateChecksumTask(manager, buffer).run()

        if checksum is None:
            manager.cancel_cell(cell)
        else:
            buffer_cache = manager.cachemanager.buffer_cache
            await validate_subcelltype(
                checksum, cell._celltype, cell._subcelltype, 
                str(cell), buffer_cache
            )
            if cell._checksum != checksum:
                manager._set_cell_checksum(cell, checksum, checksum is None)
                CellUpdateTask(manager, self.cell).launch()
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.evaluate import evaluation_cache_1
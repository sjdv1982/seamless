from . import Task

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
        lock = await taskmanager.acquire_cell_lock(cell)
        try:
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
            if checksum is not None:
                buffer_cache = manager.cachemanager.buffer_cache
                await validate_subcelltype(
                    checksum, cell._celltype, cell._subcelltype, 
                    str(cell), buffer_cache
                )
                checksum_cache[checksum] = buffer
                buffer_cache.incref(checksum)
                propagate_simple_cell(manager.livegraph, self.cell)
                manager._set_cell_checksum(self.cell, checksum, False)
                CellUpdateTask(manager, self.cell).launch()
            else:
                manager.cancel_cell(cell, True, StatusReasonEnum.UNDEFINED)
        finally:
            taskmanager.release_cell_lock(cell, lock)
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.evaluate import evaluation_cache_1
from ...protocol.calculate_checksum import checksum_cache
from ...status import StatusReasonEnum
from ...cell import text_types
from ..propagate import propagate_simple_cell
import traceback
from . import Task

class SetCellBufferTask(Task):
    # For buffers that come from the command line
    def __init__(self, manager, cell, buffer, checksum):
        assert isinstance(buffer, bytes)
        super().__init__(manager)
        self.cell = cell
        self.buffer = buffer      
        self.checksum = checksum
        self.dependencies.append(cell)

    async def _run(self):
        from . import DeserializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        taskmanager = manager.taskmanager
        livegraph = manager.livegraph
        buffer_cache = manager.cachemanager.buffer_cache
        cell = self.cell
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        cell = self.cell
        buffer = self.buffer
        checksum = self.checksum
        lock = await taskmanager.acquire_cell_lock(cell)
        try:
            if checksum is None and buffer is not None:
                checksum = await CalculateChecksumTask(manager, buffer).run()
            elif buffer is None and checksum is not None:
                buffer = buffer_cache.get_buffer(checksum)
            if checksum is None or buffer is None:
                manager.cancel_cell(cell, True, StatusReasonEnum.UNDEFINED)
            else:
                if (checksum, cell._celltype) not in evaluation_cache_1:
                    await DeserializeBufferTask(
                        manager, buffer,
                        checksum, cell._celltype, copy=False
                    ).run()
                await validate_subcelltype(
                    checksum, cell._celltype, cell._subcelltype, 
                    str(cell), buffer_cache
                )
                checksum_cache[checksum] = buffer
                buffer_cache.incref(checksum)
                propagate_simple_cell(manager.livegraph, self.cell)
                manager._set_cell_checksum(self.cell, checksum, False)
                livegraph.cell_parsing_exceptions.pop(cell, None)
                CellUpdateTask(manager, self.cell).launch()
        except Exception as exc:
            exc = traceback.format_exc()
            livegraph.cell_parsing_exceptions[cell] = exc
        finally:
            taskmanager.release_cell_lock(cell, lock)
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.evaluate import evaluation_cache_1
from ...protocol.calculate_checksum import checksum_cache
from ...status import StatusReasonEnum
from ..propagate import propagate_simple_cell
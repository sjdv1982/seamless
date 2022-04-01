import traceback
import asyncio
from . import Task

class SetCellBufferTask(Task):
    # For buffers that come from the command line
    def __init__(self, manager, cell, buffer, checksum):
        assert isinstance(buffer, bytes)
        super().__init__(manager)
        self.cell = cell
        self.buffer = buffer
        self.checksum = checksum
        self._dependencies.append(cell)

    async def _run(self):
        from . import DeserializeBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        livegraph = manager.livegraph
        cell = self.cell
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        cell = self.cell
        buffer = self.buffer
        checksum = self.checksum
        await taskmanager.await_cell(cell, self.taskid, self._root())
        try:
            if checksum is None and buffer is not None:
                checksum = await CalculateChecksumTask(manager, buffer).run()
            elif buffer is None and checksum is not None:
                buffer = get_buffer(checksum, remote=True)
            if checksum is None or buffer is None:
                manager.cancel_cell(cell, True, StatusReasonEnum.UNDEFINED, origin_task=self)
            else:
                if not has_validated_evaluation(checksum, cell._celltype):
                    await DeserializeBufferTask(
                        manager, buffer,
                        checksum, cell._celltype, copy=False
                    ).run()
                manager.cancel_cell(cell, void=False, origin_task=self)
                checksum_cache[checksum] = buffer
                buffer_cache.cache_buffer(checksum, buffer)
                manager._set_cell_checksum(self.cell, checksum, False)
                livegraph.cell_parsing_exceptions.pop(cell, None)
                CellUpdateTask(manager, self.cell).launch()
        except asyncio.CancelledError as exc:
            if self._canceled:
                raise exc from None
            exc = traceback.format_exc()
            manager.cancel_cell(self.cell, void=True, origin_task=self, reason=StatusReasonEnum.INVALID)
            livegraph.cell_parsing_exceptions[cell] = exc
        except Exception as exc:
            if isinstance(exc, ValueError):
                exc = str(type(exc).__name__) + ": " + str(exc)
            else:
                exc = traceback.format_exc()
            manager.cancel_cell(self.cell, void=True, origin_task=self, reason=StatusReasonEnum.INVALID)
            livegraph.cell_parsing_exceptions[cell] = exc
        return None

from ...protocol.calculate_checksum import checksum_cache
from ...protocol.evaluate import has_validated_evaluation
from ...status import StatusReasonEnum
from ...cache.buffer_cache import buffer_cache
from ...protocol.get_buffer import get_buffer
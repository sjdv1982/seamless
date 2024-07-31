import traceback
import asyncio

from seamless import Checksum
from . import Task

class SetCellBufferTask(Task):
    # For buffers that come from an interactive modification
    def __init__(self, manager, cell, buffer, checksum:Checksum):
        assert isinstance(buffer, bytes)
        super().__init__(manager)
        self.cell = cell
        self.buffer = buffer
        self.checksum = Checksum(checksum)
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
            if not checksum and buffer is not None:
                checksum = await CalculateChecksumTask(manager, buffer).run()
                checksum = Checksum(checksum)
            elif buffer is None and checksum:
                buffer = get_buffer(checksum, remote=True)
            if (checksum) or buffer is None:
                manager.cancel_cell(cell, True, StatusReasonEnum.UNDEFINED, origin_task=self)
            else:
                if not has_validated_evaluation(checksum, cell._celltype):
                    value = await DeserializeBufferTask(
                        manager, buffer,
                        checksum, cell._celltype, copy=False
                    ).run()
                    validate_text(value, cell._celltype, "".join(cell.path))
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

from seamless.buffer.cached_calculate_checksum import checksum_cache
from seamless.buffer.evaluate import has_validated_evaluation, validate_text
from ...status import StatusReasonEnum
from seamless.buffer.buffer_cache import buffer_cache
from seamless.buffer.get_buffer import get_buffer
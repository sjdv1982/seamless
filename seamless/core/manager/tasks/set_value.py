import traceback
from . import Task
import asyncio
import numpy as np

class SetCellValueTask(Task):
    # For values that come from the command line
    def __init__(self, manager, cell, value, *, origin_reactor=None):
        super().__init__(manager)
        self.cell = cell
        self.value = value
        self.origin_reactor = origin_reactor
        self._dependencies.append(cell)

    async def _run(self):
        from . import SerializeToBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        livegraph = manager.livegraph
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        cell = self.cell
        await taskmanager.await_cell(cell, self.taskid, self._root())
        try:
            taskmanager.cell_to_value[cell] = self.value
            value = self.value
            hash_pattern = cell._hash_pattern
            if hash_pattern is not None:
                old_deep_checksum = cell._checksum
                old_deep_value = await GetBufferTask(
                    manager, old_deep_checksum
                ).run()
                new_deep_value, _ = await value_to_deep_structure(
                    value, hash_pattern
                )
                value = new_deep_value

            checksum = None
            if value is not None:
                task = SerializeToBufferTask(
                    manager, value, cell._celltype,
                    use_cache=False
                ).run()
                try:
                    buffer = await task
                except ValueError as exc:
                    raise ValueError(exc) from None
                except asyncio.CancelledError as exc:
                    raise exc from None
                except Exception as exc:
                    raise exc from None
                assert buffer is None or isinstance(buffer, bytes)
                checksum = await CalculateChecksumTask(manager, buffer).run()
            if checksum is not None:
                buffer_cache.guarantee_buffer_info(checksum, cell._celltype)
                if isinstance(value, np.ndarray):
                    buffer_cache.update_buffer_info(checksum, "shape", value.shape, update_remote=False)
                    buffer_cache.update_buffer_info(checksum, "dtype", str(value.dtype))
                validate_evaluation_subcelltype(
                    checksum, buffer,
                    cell._celltype, cell._subcelltype,
                    str(cell)
                )
                manager.cancel_cell(cell, void=False, origin_task=self)
                checksum_cache[checksum] = buffer
                buffer_cache.cache_buffer(checksum, buffer)                
                manager._set_cell_checksum(self.cell, checksum, False)
                livegraph.cell_parsing_exceptions.pop(cell, None)
                CellUpdateTask(manager, cell, origin_reactor=self.origin_reactor).launch()
            else:
                manager.cancel_cell(cell, True, reason=StatusReasonEnum.UNDEFINED, origin_task=self)
        except asyncio.CancelledError as exc:
            if self._canceled:
                raise exc from None
            exc = traceback.format_exc()
            livegraph.cell_parsing_exceptions[self.cell] = exc
            manager.cancel_cell(self.cell, True, reason=StatusReasonEnum.INVALID, origin_task=self)
        except Exception as exc:
            exc = traceback.format_exc()
            manager.cancel_cell(self.cell, True, reason=StatusReasonEnum.INVALID, origin_task=self)
            livegraph.cell_parsing_exceptions[self.cell] = exc
        finally:
            taskmanager.cell_to_value.pop(cell, None)
        return None

from ...protocol.evaluate import validate_evaluation_subcelltype
from ...protocol.calculate_checksum import checksum_cache
from ...status import StatusReasonEnum
from ...protocol.deep_structure import value_to_deep_structure
from .get_buffer import GetBufferTask
from ...cache.buffer_cache import buffer_cache
import traceback
from . import Task
from asyncio import CancelledError

class SetCellValueTask(Task):
    # For values that come from the command line
    def __init__(self, manager, cell, value):
        super().__init__(manager)
        self.cell = cell
        self.value = value
        self.dependencies.append(cell)

    async def _run(self):
        from . import SerializeToBufferTask, CalculateChecksumTask, CellUpdateTask
        manager = self.manager()
        taskmanager = manager.taskmanager
        livegraph = manager.livegraph
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        cell = self.cell
        lock = await taskmanager.acquire_cell_lock(cell)
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

            task = SerializeToBufferTask(
                manager, value, cell._celltype,
                use_cache=False
            ).run()
            try:
                buffer = await task
            except ValueError as exc:
                raise ValueError(exc) from None
            except Exception as exc:
                raise exc from None
            assert buffer is None or isinstance(buffer, bytes)
            checksum = await CalculateChecksumTask(manager, buffer).run()
            if checksum is not None:
                await validate_subcelltype(
                    checksum, cell._celltype, cell._subcelltype,
                    str(cell)
                )
                checksum_cache[checksum] = buffer
                buffer_cache.cache_buffer(checksum, buffer)
                manager._set_cell_checksum(self.cell, checksum, False)
                livegraph.cell_parsing_exceptions.pop(cell, None)
                CellUpdateTask(manager, self.cell).launch()
            else:
                manager.cancel_cell(self.cell, True, reason=StatusReasonEnum.UNDEFINED)
        except CancelledError:
            pass
        except Exception as exc:
            exc = traceback.format_exc()
            livegraph.cell_parsing_exceptions[self.cell] = exc
            manager.cancel_cell(self.cell, True, reason=StatusReasonEnum.INVALID)
        finally:
            taskmanager.release_cell_lock(cell, lock)
            taskmanager.cell_to_value.pop(cell, None)
        return None

from ...protocol.validate_subcelltype import validate_subcelltype
from ...protocol.calculate_checksum import checksum_cache
from ...status import StatusReasonEnum
from ...protocol.deep_structure import value_to_deep_structure
from .checksum import CellChecksumTask
from .get_buffer import GetBufferTask
from ...cache.buffer_cache import buffer_cache
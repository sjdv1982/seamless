import asyncio
from . import Task, BackgroundTask
from ...protocol.calculate_checksum import calculate_checksum

class CalculateChecksumTask(BackgroundTask):
    @property
    def refkey(self):
        return id(self.buffer)

    def __init__(self, manager, buffer):
        self.buffer = buffer
        super().__init__(manager)

    async def _run(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        result = await calculate_checksum(self.buffer)
        return result


class CellChecksumTask(Task):
    """Makes sure that the cell's checksum is current"""

    def __init__(self, manager, cell):
        self.cell = cell
        super().__init__(manager)
        self._dependencies.append(cell)

    async def _run(self):
        taskmanager = self.manager().taskmanager
        cell = self.cell
        await taskmanager.await_upon_connection_tasks(self.taskid, self._root())
        await taskmanager.await_cell(cell, self.taskid, self._root())

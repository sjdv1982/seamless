import asyncio

from . import Task

class UponConnectionTask(Task):
    def __init__(self, manager, source, source_subpath, target, target_subpath):
        self.source = source
        self.source_subpath = source_subpath
        self.target = target
        self.target_subpath = target_subpath
        super().__init__(manager)
        self.dependencies.append(source)
        self.dependencies.append(target)

    def _connect_cell_cell(self):
        source, target, source_subpath, target_subpath = (
          self.source, self.target, self.source_subpath, self.target_subpath
        )
        livegraph = self.manager().livegraph
        if source_subpath is None and target_subpath is None:
            # simple cell-cell
            return livegraph.connect_cell_cell(source, target)
        raise NotImplementedError # livegraph branch

    def _connect_cell(self):        
        if isinstance(self.target, Cell):
            return self._connect_cell_cell()
        raise NotImplementedError # livegraph branch

    async def _run(self):
        """Perform actions upon connection.

- Cancel any set-cell-value tasks on the target (if a cell)
- Await all other UponConnectionTasks
  Inform authoritymanager, caches etc., returning an accessor.
  This accessor will automatically be updated if anything modifies the source
  (even if it is already running, but not finished, now)
- Launch an accessor update task
"""
        manager = self.manager()
        taskmanager = manager.taskmanager

        target = self.target
        if isinstance(target, Cell):
            cancel_tasks = []
            for task in taskmanager.cell_to_task[target]:
                if isinstance(task, SetCellValueTask):
                    cancel_tasks.append(task)
            for task in cancel_tasks:
                task.cancel()

        await taskmanager.await_upon_connection_tasks(origin_task=self)

        if isinstance(self.source, Cell):
            accessor = self._connect_cell()
            assert accessor is not None
            CellUpdateTask(manager, self.source).launch()
        else:
            raise NotImplementedError #livegraph branch
    

from .cell_update import CellUpdateTask
from .set_value import SetCellValueTask
from ...cell import Cell
import weakref
import asyncio
from functools import partial

class TaskManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.loop = asyncio.get_event_loop()
        self.tasks = []
        self.cell_to_task = {} # tasks that depend on cells
        self.reftasks = {}
        self.rev_reftasks = {}
        self.cell_to_value = {}

    def register_cell(self, cell):
        self.cell_to_task[cell] = []

    def add_task(self, task):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        if task.manager() is None:
            return task
        assert task.manager() is manager
        assert task.future is not None
        
        self.tasks.append(task)
        task.future.add_done_callback(
            partial(self._clean_task, task)
        )

        for dep in task.dependencies:
            self._add_dep(dep, task)

    def _add_dep(self, dep, task):
        if isinstance(dep, Cell):
            d = self.cell_to_task
        else:
            raise TypeError(dep)
        dd = d[dep]
        
        dd.append(task)

    def _clean_dep(self, dep, task):
        if isinstance(dep, Cell):
            d = self.cell_to_task
        else:
            raise TypeError(dep)
        dd = d[dep]

        try:
            dd.remove(task)
        except ValueError:
            pass     
    
    def cancel_task(self, task):
        if task.future is None or task.future.cancelled():
            return
        if task._realtask is not None:
            task.cancel()
        else:
            task.future.cancel() # will call _clean_task soon
    
    def _clean_task(self, task, future):
        self.tasks.remove(task)        
        for dep in task.dependencies:
            self._clean_dep(dep, task)
        for refholder in task.refholders:
            refholder.cancel()
        if task.future is not None and not task._awaiting:
            task.future.result() # to raise Exception; TODO: log it instead

    def destroy_cell(self, cell):
        for task in self.cell_to_task.get(cell, []):
            task.cancel()
        self.cell_to_task.pop(cell)
        self.cell_to_value.pop(cell, None)


from ..cell import Cell

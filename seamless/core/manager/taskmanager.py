import weakref

class BaseTask:
    def __init__(self, taskmanager):
        self.taskmanager = weakref.ref(taskmanager)
        self.deps = []
        self.future = None

    def add_dependency(self, dep):
        taskmanager = self.taskmanager()
        if taskmanager is None:
            return
        if isinstance(dep, Cell):
            cell = dep
            if cell not in taskmanager.cell_to_task:
                taskmanager.cell_to_task[cell] = []
            taskmanager.cell_to_task.append(self)
            self.deps.append(cell)

    def cancel(self):
        if self.future is not None:
            self.future.cancel()
            self.future = None
        self.destroy()

    def destroy(self):
        taskmanager = self.taskmanager()
        if taskmanager is None:
            return
        for dep in self.deps:
            if isinstance(dep, Cell):
                cell = dep
                tasks = taskmanager.cell_to_task[cell]
                tasks.remove(self)
                if not len(tasks):
                    taskmanager.cell_to_task.pop(cell)
        taskmanager.tasks.remove(self)

class TaskManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.tasks = []
        self.cell_to_task = {} # tasks that depend on cells
    
    def destroy_cell(self, cell):
        for task in self.cell_to_task.get(cell, []):
            task.cancel()


from ..cell import Cell
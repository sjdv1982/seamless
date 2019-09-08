from . import Task

print("TODO: tasks/structured_cell.py: task to deserialize editchannel, then structured_cell.set_auth_path")

class StructuredCellJoinTask(Task):    
    def __init__(self, manager, structured_cell):
        super().__init__(manager)
        self.structured_cell = structured_cell
        self.dependencies.append(structured_cell)

    async def await_sc_tasks(self):
        sc = self.structured_cell
        manager = self.manager()
        taskmanager = manager.taskmanager
        tasks = []
        for task in taskmanager.tasks:
            if sc not in task.dependencies:
                continue
            if task.taskid >= taskid or task.future is None:
                continue
            tasks.append(task)
        if len(tasks):
            await taskmanager.await_tasks(tasks)


    async def _run(self):
        sc = self.structured_cell
        await self.await_sc_tasks()
        raise NotImplementedError # livegraph branch
        # ...
        """
        Most challenging part is to put this in a Backend that:
        - Supports hash patterns
        - Computes values on demand, coming from validator code)        
        - Computes form and storage on demand, coming from form validation rules
        Fortunately, ***mixed buffers store form and storage!!!***
        Also, Backend can be read-only!
        """
        sc.modified_auth_paths.clear()

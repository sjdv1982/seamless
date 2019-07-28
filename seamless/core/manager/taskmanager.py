import weakref
import asyncio
from asyncio import CancelledError
from functools import partial
import time

class TaskManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.loop = asyncio.get_event_loop()
        self.tasks = []
        self.synctasks = []
        self.cell_to_task = {} # tasks that depend on cells
        self.accessor_to_task = {} # tasks that depend on accessors
        self.hexpression_to_task = {} # tasks that depend on expressions
        self.transformation_to_task = {} # tasks that depend on transformations
        self.reftasks = {}
        self.rev_reftasks = {}
        self.cell_to_value = {}

    def register_cell(self, cell):
        assert cell not in self.cell_to_task
        self.cell_to_task[cell] = []

    def register_accessor(self, accessor):
        assert accessor not in self.accessor_to_task
        self.accessor_to_task[accessor] = []

    def register_expression(self, expression):
        hexpression = expression.get_hash()
        assert hexpression not in self.hexpression_to_task
        self.hexpression_to_task[hexpression] = []

    def run_synctasks(self):
        synctasks = self.synctasks
        self.synctasks = []
        for synctask in synctasks:
            callback, args, kwargs = synctask
            try:
                callback(*args, **kwargs)
            except:
                import traceback
                traceback.print_exc()

    def add_synctask(self, callback, args, kwargs):
        self.synctasks.append((callback, args, kwargs))

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
        elif isinstance(dep, ReadAccessor):
            d = self.accessor_to_task
        elif isinstance(dep, Expression):
            d = self.hexpression_to_task
            dep = dep.get_hash()
        else:
            raise TypeError(dep)
        dd = d[dep]
        
        dd.append(task)

    def _get_upon_connection_tasks(self):
        for task in self.tasks:
            if isinstance(task, UponConnectionTask):
                yield task

    async def await_upon_connection_tasks(self, origin_task=None):
        futures = []
        for task in self._get_upon_connection_tasks():
            if task is origin_task or task.future is None:
                continue
            futures.append(asyncio.shield(task.future))
        if len(futures):
            try:
                await asyncio.gather(*futures)
            except:
                # If anything goes wrong in another task, consider this a cancel
                raise CancelledError

    def _clean_dep(self, dep, task):
        if isinstance(dep, Cell):
            d = self.cell_to_task
        elif isinstance(dep, ReadAccessor):
            d = self.accessor_to_task
        elif isinstance(dep, Expression):
            d = self.hexpression_to_task
            dep = dep.get_hash()
        else:
            raise TypeError(dep)
        dd = d[dep]

        try:
            dd.remove(task)
        except ValueError:
            pass

    def equilibrate(self, timeout, report):        
        if timeout is not None:
            timeout_time = time.time() + timeout
            remaining = timeout
        if report is not None:
            last_report = time.time()
        
        def select_pending_tasks():
            tasks, futures = [], []            
            for task in self.tasks:
                future = task.future
                if future is None:
                    continue
                #if future.done(): # done callback has not been completed...
                #    continue
                tasks.append(task)
                futures.append(future)
            return tasks, futures

        tasks, futures = select_pending_tasks()
        def print_report():
            running = set()
            for task in tasks:
                for dep in task.dependencies:
                    if isinstance(dep, SeamlessBase):
                        running.add(dep)
                        print(task)
            if not len(running):
                if not len(tasks):
                    return
                print("Waiting for background tasks")
                return
            result = sorted(running, key=lambda dep: dep.path)
            print("Waiting for:",end=" ")            
            for obj in result:
                print(obj,end=" ")
            print()
            return result

        while len(tasks):
            if timeout is not None:
                if report is not None:
                    curr_timeout=min(remaining, report)
                else:
                    curr_timeout = remaining
            else:
                if report is not None:
                    curr_timeout = report
                else:
                    curr_timeout = None
            asyncio.wait(
                futures,
                timeout=curr_timeout,
                return_when=asyncio.FIRST_COMPLETED
            )
            self.loop.run_until_complete(asyncio.sleep(0))
            tasks, futures = select_pending_tasks()
            if curr_timeout is not None:
                curr_time = time.time()
            if report is not None:
                if curr_time > last_report + report:
                    print_report()
                    last_report = curr_time
            if timeout is not None:
                remaining = timeout_time - time.time()
                if remaining < 0:
                    break
        return print_report()
    
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
        if task.future is not None and not task._awaiting and task.future.done():
            try:
                task.future.result() # to raise Exception; TODO: log it instead
            except CancelledError:
                pass
        refkey = self.rev_reftasks.pop(task, None)
        if refkey is not None:
            self.reftasks.pop(refkey)

    def cancel_cell(self, cell, origin_task=None):
        """Cancels all tasks depending on cell.
If origin_task is provided, that task is not cancelled."""
        for task in self.cell_to_task.get(cell, []):
            if task is origin_task:
                continue
            task.cancel()

    def cancel_accessor(self, accessor, origin_task=None):
        """Cancels all tasks depending on accessor.
If origin_task is provided, that task is not cancelled."""        
        for task in self.accessor_to_task.get(accessor, []):
            if task is origin_task:
                continue
            task.cancel()

    def cancel_expression(self, expression):
        """Cancels all tasks depending on expression."""
        hexpression = expression.get_hash()
        for task in self.hexpression_to_task[hexpression]:
            task.cancel()

    def destroy_cell(self, cell):
        self.cancel_cell(cell)
        self.cell_to_task.pop(cell)
        self.cell_to_value.pop(cell, None)

    def destroy_accessor(self, accessor):
        self.cancel_accessor(accessor)
        self.accessor_to_task.pop(accessor)

    def destroy_expression(self, expression):
        self.cancel_expression(expression)
        hexpression = expression.get_hash()
        self.hexpression_to_task.pop(hexpression)

    def check_destroyed(self):
        attribs = (
            "tasks",
            "cell_to_task",
            "accessor_to_task",
            "hexpression_to_task",
            "transformation_to_task",
            "reftasks",
            "rev_reftasks",
            "cell_to_value",
        )
        name = self.__class__.__name__        
        for attrib in attribs:
            a = getattr(self, attrib)
            if len(a):
                print(name + ", " + attrib + ": %d undestroyed"  % len(a))



from ..cell import Cell
from .. import SeamlessBase
from .accessor import ReadAccessor
from .expression import Expression
from .tasks.upon_connection import UponConnectionTask
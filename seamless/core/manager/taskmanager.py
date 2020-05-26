import weakref
import asyncio
from asyncio import CancelledError
from functools import partial
import threading
import time

from .. import destroyer

import sys
def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

class TaskManager:
    _destroyed = False
    _active = True
    _task_id_counter = 0

    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.loop = asyncio.get_event_loop()
        self.tasks = []
        self.synctasks = []
        self.cell_to_task = {} # tasks that depend on cells
        self.accessor_to_task = {}  # ...
        self.expression_to_task = {}
        self.transformer_to_task = {}
        self.reactor_to_task = {}
        self.macro_to_task = {}
        self.macropath_to_task = {}
        self.structured_cell_to_task = {}
        self.reftasks = {} # tasks that hold a reference to (are a link to) another task
        self.rev_reftasks = {} # mapping of a task to their refholder tasks
        self.cell_to_value = {} # very short term cache:
                                # only while the checksum is being computed by a SetCellValueTask
        self.cell_locks = {} # The following tasks are in-order; they must acquire this lock
                             # SetCellValue, SetCellBuffer, SetCellPath, CellChecksum
        self._destroying = set()

    def activate(self):
        self._active = True

    def deactivate(self):
        """Deactivate the task manager.
        Running tasks are unaffected, but all future tasks (including those launched by running tasks)
         will only commence after the task manager has been activated again."""
        self._active = False

    async def await_active(self):
        while not self._active:
            await asyncio.sleep(0.01)

    def register_cell(self, cell):
        assert cell not in self.cell_to_task
        self.cell_locks[cell] = []
        self.cell_to_task[cell] = []

    def register_structured_cell(self, structured_cell):
        self.structured_cell_to_task[structured_cell] = []

    def register_accessor(self, accessor):
        assert accessor not in self.accessor_to_task
        self.accessor_to_task[accessor] = []

    def register_expression(self, expression):
        assert expression not in self.expression_to_task
        self.expression_to_task[expression] = []

    def register_transformer(self, transformer):
        assert transformer not in self.transformer_to_task
        self.transformer_to_task[transformer] = []

    def register_reactor(self, reactor):
        assert reactor not in self.reactor_to_task
        self.reactor_to_task[reactor] = []

    def register_macropath(self, macropath):
        assert macropath not in self.macropath_to_task
        self.macropath_to_task[macropath] = []

    def register_macro(self, macro):
        assert macro not in self.macro_to_task
        self.macro_to_task[macro] = []

    def run_synctasks(self):
        synctasks = self.synctasks
        if not len(synctasks):
            return
        self.synctasks = []
        for synctask in synctasks:
            callback, args, kwargs, event = synctask
            try:
                result = callback(*args, **kwargs)
            except Exception:
                result = None
                import traceback
                traceback.print_exc()
            if event is not None:
                event.custom_result_value = result # hackish
                event.set()

    async def loop_run_synctasks(self):
        while not self._destroyed:
            try:
                self.run_synctasks()
            except Exception:
                import traceback
                traceback.print_exc()
            await asyncio.sleep(0.0001)

    def add_synctask(self, callback, args, kwargs, with_event):
        event = None
        if with_event:
            event = threading.Event()
        self.synctasks.append((callback, args, kwargs, event))
        return event

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
        elif isinstance(dep, StructuredCell):
            d = self.structured_cell_to_task
        elif isinstance(dep, ReadAccessor):
            d = self.accessor_to_task
        elif isinstance(dep, Expression):
            d = self.expression_to_task
        elif isinstance(dep, Transformer):
            d = self.transformer_to_task
        elif isinstance(dep, Reactor):
            d = self.reactor_to_task
        elif isinstance(dep, Macro):
            d = self.macro_to_task
        elif isinstance(dep, MacroPath):
            d = self.macropath_to_task
        else:
            raise TypeError(type(dep))
        dd = d[dep]

        dd.append(task)

    def _get_upon_connection_tasks(self, root):
        for task in self.tasks:
            if isinstance(task, UponConnectionTask):
                if task._root() is root:
                    yield task

    async def await_upon_connection_tasks(self,taskid,root):
        futures, tasks = [], []
        for task in self._get_upon_connection_tasks(root):
            if task.taskid >= taskid or task.future is None:
                continue
            tasks.append(task)
        if len(tasks):
            await self.await_tasks(tasks)

    @staticmethod
    async def await_tasks(tasks, shield=False):
        """Wait for taskmanager Tasks. Any cancel will raise CancelError, unless shield is True"""
        futures = []
        for task in tasks:
            futures.append(
                asyncio.shield(task.future)
            )
        await asyncio.wait(futures)
        ok = True
        for task, fut in zip(tasks, futures):
            try:
                fut.result() # to get rid of "Future exception was never retrieved (does not always work!)"
                                # since the shield has its own exception
            except Exception as exc:
                pass

            try:
                task.future.result() # This is the real future
            except Exception as exc:
                if not isinstance(exc, CancelledError):
                    if task._awaiting:
                        continue
                    ###import traceback
                    ###traceback.print_exc()
                task._awaiting = True
                # If anything goes wrong in another task, consider this a cancel
                ok = False
        if not ok and not shield:
            raise CancelledError

    async def acquire_cell_lock(self, cell):
        if cell._destroyed:
            return
        locks = self.cell_locks[cell]
        if not len(locks):
            id = 1
        else:
            id = locks[-1] + 1
        locks.append(id)
        while locks[0] != id:
            await asyncio.sleep(0.0001)   # 0.1 ms
        return id

    def release_cell_lock(self, cell, id):
        if cell._destroyed:
            return
        locks = self.cell_locks[cell]
        locks.remove(id)

    def _clean_dep(self, dep, task):
        if isinstance(dep, Cell):
            d = self.cell_to_task
        elif isinstance(dep, StructuredCell):
            d = self.structured_cell_to_task
        elif isinstance(dep, ReadAccessor):
            d = self.accessor_to_task
        elif isinstance(dep, Expression):
            d = self.expression_to_task
        elif isinstance(dep, Transformer):
            d = self.transformer_to_task
        elif isinstance(dep, Reactor):
            d = self.reactor_to_task
        elif isinstance(dep, Macro):
            d = self.macro_to_task
        elif isinstance(dep, MacroPath):
            d = self.macropath_to_task
        else:
            raise TypeError(dep)
        dd = d.get(dep)
        if dd is None:
            return

        try:
            dd.remove(task)
        except ValueError:
            pass

    def compute(self, timeout, report, get_tasks_func=None):
        assert nest_asyncio is not None or not asyncio.get_event_loop().is_running()
        manager = self.manager()
        manager.temprefmanager.purge()

        if timeout is not None:
            timeout_time = time.time() + timeout
            remaining = timeout
        if report is not None and report > 0:
            last_report = time.time()

        def select_pending_tasks():
            if get_tasks_func is None:
                tasks = self.tasks
            else:
                tasks = get_tasks_func(self)
            ptasks, futures = [], []
            for task in tasks:
                future = task.future
                if future is None:
                    continue
                ptasks.append(task)
                futures.append(future)
            return ptasks, futures

        ptasks, futures = select_pending_tasks()
        def print_report(verbose=True):
            running = set()
            #print("TASKS", ptasks)
            for task in ptasks:
                for dep in task.dependencies:
                    if isinstance(dep, SeamlessBase):
                        running.add(dep)
                        #print("TASK",task)
            if not len(running):
                if not len(ptasks):
                    return [], False
                if verbose:
                    print("Waiting for background tasks")
                return [], True
            result = sorted(running, key=lambda dep: dep.path)
            if verbose:
                print("Waiting for:",end=" ")
                for obj in result:
                    print(obj,end=" ")
                print()
            return result, True

        while len(ptasks):
            if timeout is not None:
                if report is not None and report > 0:
                    curr_timeout=min(remaining, report)
                else:
                    curr_timeout = remaining
            else:
                if report is not None and report > 0:
                    curr_timeout = report
                else:
                    curr_timeout = None
            self.loop.run_until_complete(asyncio.sleep(0.0001))
            ptasks, futures = select_pending_tasks()
            if curr_timeout is not None:
                curr_time = time.time()
            if report is not None and report > 0:
                if curr_time > last_report + report:
                    print_report()
                    last_report = curr_time
            if timeout is not None:
                remaining = timeout_time - time.time()
                if remaining < 0:
                    break
        return print_report(verbose=False)

    async def computation(self, timeout, report, get_tasks_func=None):
        manager = self.manager()
        manager.temprefmanager.purge()

        if timeout is not None:
            timeout_time = time.time() + timeout
            remaining = timeout
        if report is not None and report > 0:
            last_report = time.time()

        def select_pending_tasks():
            if get_tasks_func is None:
                tasks = self.tasks
            else:
                tasks = get_tasks_func(self)
            ptasks, futures = [], []
            for task in tasks:
                future = task.future
                if future is None:
                    continue
                ptasks.append(task)
                futures.append(future)
            return ptasks, futures

        ptasks, futures = select_pending_tasks()
        def print_report(verbose=True):
            running = set()
            #print("TASKS", ptasks)
            for task in ptasks:
                for dep in task.dependencies:
                    if isinstance(dep, SeamlessBase):
                        running.add(dep)
                        #print("TASK",task)
            if not len(running):
                if not len(ptasks):
                    return [], False
                if verbose:
                    print("Waiting for background tasks")
                return [], True
            result = sorted(running, key=lambda dep: dep.path)
            if verbose:
                print("Waiting for:",end=" ")
                for obj in result:
                    print(obj,end=" ")
                print()
            return result, True

        while len(ptasks):
            if timeout is not None:
                if report is not None and report > 0:
                    curr_timeout=min(remaining, report)
                else:
                    curr_timeout = remaining
            else:
                if report is not None and report > 0:
                    curr_timeout = report
                else:
                    curr_timeout = None
            await asyncio.sleep(0.0001)
            ptasks, futures = select_pending_tasks()
            if curr_timeout is not None:
                curr_time = time.time()
            if report is not None and report > 0:
                if curr_time > last_report + report:
                    print_report()
                    last_report = curr_time
            if timeout is not None:
                remaining = timeout_time - time.time()
                if remaining < 0:
                    break
        return print_report(verbose=False)

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
        if task.future is not None and task.future.done():
            fut = task.future
            fut._log_traceback = False
            if not task._awaiting:
                try:
                    assert task.future is fut
                    assert not task.future._log_traceback
                    task.future.result() # to raise Exception; TODO: log it instead
                except CancelledError:
                    try:
                        task.future._exception = None ### KLUDGE
                    except AttributeError:
                        pass
                    pass
                finally:
                    task._awaiting = True
        for refholder in task.refholders:
            refholder.cancel()
        refkey = self.rev_reftasks.pop(task, None)
        if refkey is not None:
            self.reftasks.pop(refkey)

    def cancel_cell(self, cell, *, origin_task=None, full=False):
        """Cancels all tasks depending on cell.
If origin_task is provided, that task is not cancelled.
If full = True, cancels all UponConnectionTasks as well"""
        for task in self.cell_to_task.get(cell, []):
            if task is origin_task:
                continue
            if not full and isinstance(task, UponConnectionTask):
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
        for task in self.expression_to_task[expression]:
            task.cancel()

    def cancel_transformer(self, transformer, full=False):
        """Cancels all tasks depending on transformer."""
        for task in self.transformer_to_task[transformer]:
            if not full and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_reactor(self, reactor, full=False):
        """Cancels all tasks depending on reactor."""
        for task in self.reactor_to_task[reactor]:
            if not full and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_macro(self, macro, full=False):
        """Cancels all tasks depending on macro."""
        for task in self.macro_to_task[macro]:
            if not full and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_macropath(self, macropath, full=False):
        """Cancels all tasks depending on macropath.
        If full = True, cancels all UponConnectionTasks as well"""
        if macropath not in self.macropath_to_task:
            return
        for task in self.macropath_to_task[macropath]:
            if not full and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_structured_cell(self, structured_cell, origin_task=None):
        tasks = self.structured_cell_to_task.get(structured_cell, [])
        for task in tasks:
            if task is origin_task:
                continue
            task.cancel()

    @destroyer
    def destroy_cell(self, cell, full=False):
        self.cancel_cell(cell, full=full)
        self.cell_to_task.pop(cell)
        self.cell_to_value.pop(cell, None)
        self.cell_locks.pop(cell)

    @destroyer
    def destroy_structured_cell(self, structured_cell):
        self.cancel_structured_cell(structured_cell)
        self.structured_cell_to_task.pop(structured_cell)

    @destroyer
    def destroy_accessor(self, accessor):
        self.cancel_accessor(accessor)
        self.accessor_to_task.pop(accessor, None) # guard here for an invalid connection

    @destroyer
    def destroy_expression(self, expression):
        self.cancel_expression(expression)
        self.expression_to_task.pop(expression)

    @destroyer
    def destroy_transformer(self, transformer, *, full=False):
        self.cancel_transformer(transformer, full=full)
        self.transformer_to_task.pop(transformer)

    def destroy_reactor(self, reactor, *, full=False):
        self.cancel_reactor(reactor, full=full)
        self.reactor_to_task.pop(reactor)

    @destroyer
    def destroy_macro(self, macro, *, full=False):
        self.cancel_macro(macro, full=full)
        self.macro_to_task.pop(macro)

    @destroyer
    def destroy_macropath(self, macropath, *, full=False):
        if macropath not in self.macropath_to_task:
            return
        self.cancel_macropath(macropath, full=full)
        self.macropath_to_task.pop(macropath)

    def check_destroyed(self):
        attribs = (
            "tasks",
            "cell_to_task",
            "accessor_to_task",
            "expression_to_task",
            "transformer_to_task",
            "reactor_to_task",
            "macro_to_task",
            "macropath_to_task",
            "reftasks",
            "rev_reftasks",
            "cell_to_value",
        )
        name = self.__class__.__name__
        for attrib in attribs:
            a = getattr(self, attrib)
            if len(a):
                log(name + ", " + attrib + ": %d undestroyed"  % len(a))

    def destroy(self):
        # just to stop the loop...
        # all items must be manually destroyed!
        self._destroyed = True

from ..cell import Cell
from ..structured_cell import StructuredCell
from ..transformer import Transformer
from ..macro import Macro, Path as MacroPath
from ..reactor import Reactor
from .. import SeamlessBase
from .accessor import ReadAccessor
from .expression import Expression
from .tasks.upon_connection import UponConnectionTask
from ...communion_server import communion_server
from ... import nest_asyncio
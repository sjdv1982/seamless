import weakref
import asyncio
from asyncio import CancelledError
from functools import partial
import threading
import time
from collections import deque
import traceback
from bisect import bisect_left

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

class TaskManager:
    _destroyed = False
    _active = True
    _task_id_counter = 0
    _last_task = 0

    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.loop = asyncio.get_event_loop()
        self.tasks = []
        self.barriers = set()  # list of taskids. Only the tasks with an id up to the barrier taskid may execute.
                               # Once all of them have been executed, the barrier is lifted
        self.launching_tasks = set()
        self.task_ids = []
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
    def activate(self):
        self._active = True

    def deactivate(self):
        """Deactivate the task manager.
        Running tasks are unaffected, but all future tasks (including those launched by running tasks)
         will only commence after the task manager has been activated again."""
        self._active = False

    async def await_active(self):
        while not self._active:
            await asyncio.sleep(0.05)

    def declare_task_finished(self, taskid):
        if self._last_task < taskid:
            self._last_task = taskid

    async def await_barrier(self, taskid):
        while 1:
            for barrier in self.barriers:
                if taskid > barrier:
                    break
            else:
                break
            if taskid == self.task_ids[0]:
                for barrier in list(self.barriers):
                    if barrier <= taskid:
                        self.barriers.discard(barrier)
                break
            await asyncio.sleep(0.001)

    def add_barrier(self):
        if self._task_id_counter == self._last_task:
            return
        self.barriers.add(self._task_id_counter)

    def register_cell(self, cell):
        assert cell not in self.cell_to_task
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

    def _run_synctasks(self):
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
                print_error(traceback.format_exc())
            if event is not None:
                event.custom_result_value = result # hackish
                event.set()

    def run_all_synctasks(self):
        while len(self.synctasks):
            self._run_synctasks()

    async def loop_run_synctasks(self):
        while not self._destroyed:
            try:
                self._run_synctasks()
            except Exception:
                print_error(traceback.format_exc())
            await asyncio.sleep(0.05)

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

        assert task not in self.tasks
        self.launching_tasks.discard(task)
        self.tasks.append(task)
        self.task_ids.append(task.taskid)
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


    async def await_upon_connection_tasks(self,taskid,root):
        while 1:
            pos = bisect_left(self.task_ids, taskid)
            """
            for n in range(pos): assert self.tasks[n].taskid < taskid, (pos, n)
            for n in range(pos, len(self.tasks)): assert self.tasks[n].taskid >= taskid, (pos, n)
            """
            for task in reversed(self.tasks[:pos]):
                if isinstance(task, UponConnectionTask):
                    if task.future is None or task.future.done():
                        continue
                    """
                    # can't happen. Every root context has its own taskmanager
                    if task._root() is not root:
                        continue
                    """
                    fut = asyncio.shield(task.future)
                    await fut
                    break
            else:
                break

    async def await_cell(self,cell,taskid,root):
        while 1:
            cell_tasks = self.cell_to_task[cell]
            if len(cell_tasks) == 0 or cell_tasks[0].taskid >= taskid:
                break
            await asyncio.sleep(0.001)

    def is_pending(self, cell):
        """Returns if a cell's checksum is pending on a auth task (set cell buffer or set cell value)
        If they do not fail, these tasks are guaranteed to call manager._set_cell_checksum.
        """
        from .tasks.set_buffer import SetCellBufferTask
        from .tasks.set_value import SetCellValueTask
        cell_tasks = self.cell_to_task[cell]
        for task in cell_tasks:
            if isinstance(task, (SetCellBufferTask, SetCellValueTask)):
                return True
        return False

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
                    print_debug(traceback.format_exc())
                task._awaiting = True
                # If anything goes wrong in another task, consider this a cancel
                ok = False
        if not ok and not shield:
            raise CancelledError

    def _clean_dep(self, dep, task):
        if isinstance(dep, Cell):
            if dep._destroyed:
                return
            d = self.cell_to_task
        elif isinstance(dep, StructuredCell):
            if dep._destroyed:
                return
            d = self.structured_cell_to_task
        elif isinstance(dep, ReadAccessor):
            d = self.accessor_to_task
            if dep not in d:
                return
        elif isinstance(dep, Expression):
            d = self.expression_to_task
            if dep not in d:
                return
        elif isinstance(dep, Transformer):
            if dep._destroyed:
                return
            d = self.transformer_to_task
        elif isinstance(dep, Reactor):
            if dep._destroyed:
                return
            d = self.reactor_to_task
        elif isinstance(dep, Macro):
            if dep._destroyed:
                return
            d = self.macro_to_task
        elif isinstance(dep, MacroPath):
            if dep._destroyed:
                return
            d = self.macropath_to_task
            if dep not in d:
                return
        else:
            raise TypeError(dep)
        dd = d[dep]
        dd.remove(task)

    def compute(self, timeout, report, get_tasks_func=None):
        assert not asyncio.get_event_loop().is_running()
        manager = self.manager()
        manager.temprefmanager.purge()
        run_mount = False
        if not len(manager.mountmanager.mounts):
            run_mount = True
        last_mount_run = manager.mountmanager.last_run

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
            return tasks

        ptasks = select_pending_tasks()
        if not len(ptasks):
            ptasks = [None]  # enter the loop at least once
        def print_report(verbose=True):
            running = set()
            #print("TASKS", ptasks)
            for task in ptasks:
                if task.future is None:
                    continue
                if verbose:
                    if logger.isEnabledFor(logging.DEBUG):
                        if task._runner is not None:
                            msg = "\n******\n"
                            msg += "WAIT FOR {} {} {}\n".format(task.__class__.__name__, hex(id(task)), task.dependencies)
                            frame = task._runner.cr_frame
                            stack = "   " + "\n   ".join(traceback.format_stack(frame))
                            msg += stack
                            msg += "******"
                            print_debug(msg)
                    else:
                        print_debug("WAIT FOR", task.__class__.__name__, hex(id(task)), task.dependencies)
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
                objs = " ".join([str(obj) for obj in result])
                print(objs)            
            return result, True

        while len(ptasks) or len(self.launching_tasks) or len(self.synctasks) or not run_mount:
            if not run_mount and manager.mountmanager.last_run != last_mount_run:
                run_mount = True
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
            try:
                self.loop.run_until_complete(asyncio.sleep(0.001))
            except KeyboardInterrupt:
                return
            ptasks = select_pending_tasks()
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
            if get_tasks_func is None:
                if not (len(self.tasks) or len(self.launching_tasks) or len(self.synctasks)):
                    cyclic_scells = manager.livegraph.get_cyclic()
                    if len(cyclic_scells):
                        changed = manager.force_join(cyclic_scells)
                        if changed:
                            self.loop.run_until_complete(asyncio.sleep(0.1))
                            ptasks = [None]  # just to prevent the loop from breaking
        waitfor, background = print_report(verbose=False)
        manager.livegraph._flush_observations()
        if not len(waitfor) and get_tasks_func is None:
            cyclic_scells = manager.livegraph.get_cyclic()
            return cyclic_scells, background
        else:
            return waitfor, background

    async def computation(self, timeout, report, get_tasks_func=None):
        manager = self.manager()
        manager.temprefmanager.purge()
        run_mount = False
        last_mount_run = manager.mountmanager.last_run
        if not len(manager.mountmanager.mounts):
            run_mount = True

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
            return tasks

        ptasks = select_pending_tasks()
        if not len(ptasks):
            ptasks = [None]  # enter the loop at least once
        def print_report(verbose=True):
            running = set()
            #print("TASKS", ptasks)
            for task in ptasks:
                if task.future is None:
                    continue
                if verbose:
                    if logger.isEnabledFor(logging.DEBUG):
                        if task._runner is not None:
                            msg = "\n******\n"
                            msg += "WAIT FOR {} {} {}\n".format(task.__class__.__name__, hex(id(task)), task.dependencies)
                            frame = task._runner.cr_frame
                            stack = "   " + "\n   ".join(traceback.format_stack(frame))
                            msg += stack
                            msg += "******"
                            print_debug(msg)
                    else:
                        print_debug("WAIT FOR", task.__class__.__name__, hex(id(task)), task.dependencies)
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
                objs = " ".join([str(obj) for obj in result])
                print(objs)
            return result, True

        while len(ptasks) or len(self.launching_tasks) or len(self.synctasks) or not run_mount:
            if not run_mount and manager.mountmanager.last_run != last_mount_run:
                run_mount = True
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
            try:
                if len(ptasks) and ptasks != [None]:
                    futures = [ptask.future for ptask in ptasks if ptask]
                    await asyncio.wait(futures, timeout=0.05)  # this can go wrong, hence the timeout
                else:
                    await asyncio.sleep(0.001)
            except KeyboardInterrupt:
                return
            ptasks = select_pending_tasks()
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
            if get_tasks_func is None:
                if not (len(self.tasks) or len(self.launching_tasks) or len(self.synctasks)):
                    cyclic_scells = manager.livegraph.get_cyclic()
                    if len(cyclic_scells):
                        changed = manager.force_join(cyclic_scells)
                        if changed:
                            await asyncio.sleep(0.1)
                            ptasks = [None]  # just to prevent the loop from breaking
        waitfor, background = print_report(verbose=False)
        manager.livegraph._flush_observations()
        if not len(waitfor) and get_tasks_func is None:
            cyclic_scells = manager.livegraph.get_cyclic()
            return cyclic_scells, background
        else:
            return waitfor, background


    def cancel_task(self, task):
        self.barriers.discard(task.taskid)
        if task.future is None or task.future.cancelled():
            self._clean_task(task, task.future)
            return
        if task._realtask is not None:
            return self.cancel_task(task._realtask)
        else:
            task.future.cancel() # will call _clean_task soon, but better do it now
            self._clean_task(task, task.future, manual=True)

    def _clean_task(self, task, future, manual=False):
        self.barriers.discard(task.taskid)
        self.declare_task_finished(task.taskid)
        if manual and task._cleaned:
            return
        cleaned = task._cleaned
        if not cleaned:
            self.tasks.remove(task)
            self.task_ids.remove(task.taskid)
            task._cleaned = True

            print_debug("FINISHED", task.__class__.__name__, task.taskid, task.dependencies)
            
            for dep in task.dependencies:
                try:
                    self._clean_dep(dep, task)
                except Exception:
                    print("ERROR in", task, task.dependencies)
                    traceback.print_exc()
            refkey = self.rev_reftasks.pop(task, None)
            if refkey is not None:
                self.reftasks.pop(refkey)

        if not manual:
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


    def cancel_cell(self, cell, *, origin_task=None, full=False):
        """Cancels all tasks depending on cell.
If origin_task is provided, that task is not cancelled.
If full = True, cancels all UponConnectionTasks as well"""
        for task in list(self.cell_to_task[cell]):
            if task is origin_task:
                continue
            if (not full) and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_accessor(self, accessor, origin_task=None):
        """Cancels all tasks depending on accessor.
If origin_task is provided, that task is not cancelled."""
        for task in list(self.accessor_to_task[accessor]):
            if task is origin_task:
                continue
            task.cancel()

    def cancel_expression(self, expression):
        """Cancels all tasks depending on expression."""
        for task in list(self.expression_to_task[expression]):
            task.cancel()

    def cancel_transformer(self, transformer, full=False):
        """Cancels all tasks depending on transformer."""
        for task in list(self.transformer_to_task[transformer]):
            if (not full) and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_reactor(self, reactor, full=False):
        """Cancels all tasks depending on reactor."""
        for task in list(self.reactor_to_task[reactor]):
            if (not full) and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_macro(self, macro, full=False):
        """Cancels all tasks depending on macro."""
        for task in list(self.macro_to_task[macro]):
            if (not full) and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_macropath(self, macropath, full=False):
        """Cancels all tasks depending on macropath.
        If full = True, cancels all UponConnectionTasks as well"""
        if macropath not in self.macropath_to_task:
            return
        for task in list(self.macropath_to_task[macropath]):
            if (not full) and isinstance(task, UponConnectionTask):
                continue
            task.cancel()

    def cancel_structured_cell(self, structured_cell, *, no_auth, origin_task=None):
        change = True
        canceled = set()
        while change:
            change = False
            not_started_auth, not_started_join = False, False
            tasks = self.structured_cell_to_task.get(structured_cell, [])
            for task in tasks:
                if task is origin_task:
                    continue
                if task in canceled:
                    continue
                if task._canceled:
                    continue
                if task.future is not None and task.future.done():
                    continue
                if no_auth:
                    if isinstance(task, StructuredCellAuthTask):
                        continue
                change = True
                canceled.add(task)
                task.cancel()

    def destroy_cell(self, cell, full=False):
        self.cancel_cell(cell, full=full)
        self.cell_to_task.pop(cell)
        self.cell_to_value.pop(cell, None)

    def destroy_structured_cell(self, structured_cell):
        self.cancel_structured_cell(structured_cell, no_auth=False)
        self.structured_cell_to_task.pop(structured_cell)

    def destroy_accessor(self, accessor):
        self.cancel_accessor(accessor)
        self.accessor_to_task.pop(accessor)

    def destroy_expression(self, expression):
        self.cancel_expression(expression)
        self.expression_to_task.pop(expression)

    def destroy_transformer(self, transformer, *, full=False):
        self.cancel_transformer(transformer, full=full)
        self.transformer_to_task.pop(transformer)

    def destroy_reactor(self, reactor, *, full=False):
        self.cancel_reactor(reactor, full=full)
        self.reactor_to_task.pop(reactor)

    def destroy_macro(self, macro, *, full=False):
        self.cancel_macro(macro, full=full)
        self.macro_to_task.pop(macro)

    def destroy_macropath(self, macropath, *, full=False):
        if macropath not in self.macropath_to_task:
            return
        self.cancel_macropath(macropath, full=full)
        self.macropath_to_task.pop(macropath)

    def check_destroyed(self):
        attribs = (
            "tasks",
            "launching_tasks",
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
        ok = True
        name = self.__class__.__name__
        for attrib in attribs:
            a = getattr(self, attrib)
            if attrib == "tasks":
                a = [aa for aa in a if not isinstance(aa, BackgroundTask)]
            if attrib == "reftasks":
                a = [aa for aa in a.values() if not isinstance(aa, BackgroundTask)]
            if attrib == "rev_reftasks":
                a = [aa for aa in a.keys() if not isinstance(aa, BackgroundTask)]
            if len(a):
                print_error(name + ", " + attrib + ": %d undestroyed"  % len(a))
                if attrib.endswith("tasks") and len(a) <= 5:
                    print_error("*" * 30)
                    for task in a:
                        print_error("Task:", task)
                        for dep in task.dependencies:
                            print_error("Depends on:", dep)
                        print_error("*" * 30)
                    print_error()
                ok = False
        return ok

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
from .tasks.structured_cell import StructuredCellAuthTask, StructuredCellJoinTask
from ...communion_server import communion_server
from .tasks import BackgroundTask
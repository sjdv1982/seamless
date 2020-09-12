import weakref
import asyncio
from asyncio import CancelledError
import traceback
from functools import partial

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

def is_equal(old, new):
    if new is None:
        return False
    if len(old) != len(new):
        return False
    for k in old:
        if old[k] != new[k]:
            return False
    return True

_evaluation_locks = [None] * 20  # twenty evaluations in parallel

def set_parallel_evaluations(evaluations):
    if len(_evaluation_locks) != evaluations:
        if any(_evaluation_locks):
            msg = "WARNING: Cannot change number of parallel evaluations from %d to %d since there are running evaluations"
            print(msg % (len(_evaluation_locks), evaluations), file=sys.stderr)
        else:
            _evaluation_locks[:] = [None] * evaluations


async def acquire_evaluation_lock(task):
    while 1:
        for locknr, lock in enumerate(_evaluation_locks):
            if lock is None:
                _evaluation_locks[locknr] = task
                return locknr
        await asyncio.sleep(0.01)

def release_evaluation_lock(locknr):
    assert _evaluation_locks[locknr] is not None
    _evaluation_locks[locknr] = None

class Task:
    _realtask = None
    _awaiting = False
    _canceled = False
    _started = False
    _cached_root = None
    future = None
    caller_count = None

    def __init__(self, manager, *args, **kwargs):
        if isinstance(manager, weakref.ref):
            manager = manager()
        assert isinstance(manager, Manager)
        self._dependencies = []
        taskmanager = manager.taskmanager
        if self.refkey is not None:
            reftask = taskmanager.reftasks.get(self.refkey)
            if reftask is not None:
                self.set_realtask(reftask)
                return
            else:
                taskmanager.reftasks[self.refkey] = self
                taskmanager.rev_reftasks[self] = self.refkey
        self.manager = weakref.ref(manager)
        self.refholders = [self] # tasks that are value-identical to this one,
                                # of which this one is the realtask

        taskmanager._task_id_counter += 1
        self.taskid = taskmanager._task_id_counter
        self.caller_count = 0

    @property
    def refkey(self):
        return None

    @property
    def dependencies(self):
        if self._realtask is not None:
            return self._realtask.dependencies
        else:
            return self._dependencies

    def _root(self):
        if self._cached_root is not None:
            return self._cached_root
        root = None
        for dep in self._dependencies:
            deproot = dep._root()
            if root is None:
                root = deproot
            elif deproot is not None:
                assert root is deproot, (root, deproot) # tasks cannot depend on multiple toplevel contexts
        self._cached_root = root
        return root

    def set_realtask(self, realtask):
        self._realtask = realtask
        realtask.refholders.append(self)

    async def run(self):
        realtask = self._realtask
        if realtask is not None:
            result = await realtask.run()
            return result
        already_launched = (self.future is not None)
        if not already_launched:
            self._launch()
            assert self.future is not None
        if self.future.done():
            return self.future.result()
        if not already_launched:
            print_debug("RUN", self.__class__.__name__, hex(id(self)))
        self._awaiting = True
        try:
            if self.caller_count != -999:
                self.caller_count += 1
            await asyncio.shield(self.future)
        except CancelledError:
            if self.caller_count != -999:
                self.caller_count -= 1
                if self.caller_count == 0:
                    print_debug("CANCELING", self.__class__.__name__, hex(id(self)))
                    self.cancel()
            raise
        if not already_launched:
            print_debug("HAS RUN", self.__class__.__name__, hex(id(self)))
        return self.future.result()

    async def _run0(self, taskmanager):
        await asyncio.shield(taskmanager.await_active())
        await asyncio.shield(communion_server.startup)
        self._started = True
        return await self._run()

    def _launch(self):
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        if self._canceled:
            return
        taskmanager = manager.taskmanager
        if self.future is not None:
            return taskmanager
        taskmanager.run_synctasks()
        print_debug("LAUNCH", self.__class__.__name__, hex(id(self)), self.dependencies)
        awaitable = self._run0(taskmanager)
        self.future = asyncio.ensure_future(awaitable)
        taskmanager.add_task(self)
        return taskmanager

    def launch(self):
        realtask = self._realtask
        if realtask is not None:
            return realtask.launch()
        if self.future is not None:
            return
        self._launch()
        self.caller_count = -999

    def launch_and_await(self):
        assert not asyncio.get_event_loop().is_running()
        realtask = self._realtask
        if realtask is not None:
            return realtask.launch_and_await()
        # Blocking version of launch
        taskmanager = self._launch()
        self._awaiting = True
        if taskmanager is None:
            raise CancelledError
        taskmanager.loop.run_until_complete(self.future)
        return self.future.result()

    def cancel_refholder(self, refholder):
        assert self._realtask is None
        self.refholders.remove(refholder)
        if not len(self.refholders):
            self.cancel()

    def cancel(self):
        if self._canceled:
            return
        self._canceled = True
        print_debug("CANCEL", self.__class__.__name__, hex(id(self)), self.dependencies)
        #import traceback; traceback.print_stack()
        realtask = self._realtask
        if realtask is not None:
            return realtask.cancel_refholder(self)
        manager = self.manager()
        if self.future is not None and self.future != "DUMMY":
            if self.future.cancelled():
                return
            self.future.cancel()
        if manager is None or manager._destroyed:
            return
        taskmanager = manager.taskmanager
        taskmanager.cancel_task(self)


from .set_value import SetCellValueTask
from .set_buffer import SetCellBufferTask
from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .checksum import CellChecksumTask, CalculateChecksumTask
from .cell_update import CellUpdateTask
from .get_buffer import GetBufferTask
from .upon_connection import UponConnectionTask, UponBiLinkTask
from ..manager import Manager
from ....communion_server import communion_server
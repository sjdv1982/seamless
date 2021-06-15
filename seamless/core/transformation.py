"""Schedules asynchronous (transformer) jobs"""
import weakref
import asyncio
import multiprocessing
import sys
import traceback
import functools
import time
import atexit
import json

from multiprocessing import Process
from .execute import Queue, execute, execute_debug
from .run_multi_remote import run_multi_remote, run_multi_remote_pair
from .injector import transformer_injector as injector
from .build_module import build_all_modules
from ..compiler import compilers as default_compilers, languages as default_languages

import logging

logger = logging.getLogger("seamless")

forked_processes = weakref.WeakKeyDictionary()
def _kill_processes():
    for process, termination_time in forked_processes.items():
        if not process.is_alive():
            continue
        kill_time = termination_time + 15  # "docker stop" has 10 secs grace, add 5 secs margin
        ctime = time.time()
        while kill_time > ctime:
            print("Waiting for transformer process to terminate...")
            time.sleep(2)
            if not process.is_alive():
                break
            ctime = time.time()
        if not process.is_alive():
            continue
        print("Killing transformer process... cleanup will not have happened!")
        process.kill()

atexit.register(_kill_processes)

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

class SeamlessTransformationError(Exception):
    pass

class SeamlessStreamTransformationError(Exception):
    pass

###############################################################################
# Local jobs
###############################################################################

_locks = [None] * multiprocessing.cpu_count()
def set_ncores(ncores):
    if len(_locks) != ncores:
        if any(_locks):
            msg = "WARNING: Cannot change ncores from %d to %d since there are running jobs"
            print(msg % (len(_locks), ncores), file=sys.stderr)
        else:
            _locks[:] = [None] * ncores

async def acquire_lock(tf_checksum):
    if not len(_locks):
        raise SeamlessTransformationError("Local computation has been disabled for this Seamless instance")
    while 1:
        for locknr, lock in enumerate(_locks):
            if lock is None:
                _locks[locknr] = tf_checksum
                return locknr
        await asyncio.sleep(0.01)

def release_lock(locknr):
    assert _locks[locknr] is not None
    _locks[locknr] = None

###############################################################################
# Remote jobs
###############################################################################

REMOTE_TIMEOUT = 5.0

class RemoteJobError(SeamlessTransformationError):
    pass

###############################################################################

class TransformationJob:
    _job_id_counter = 0
    _cancelled = False
    _hard_cancelled = False
    remote_futures = None
    start = None
    def __init__(self,
        checksum, codename,
        transformation,
        semantic_cache, debug,
        python_debug
    ):
        self.checksum = checksum
        assert codename is not None
        self.codename = codename
        assert "code" in transformation, transformation.keys()
        for pinname in transformation:
            if pinname in ("__compilers__", "__languages__"):
                continue
            if pinname != "__output__":
                assert transformation[pinname][2] is not None, pinname
        outputpin = transformation["__output__"]
        outputname, celltype, subcelltype = outputpin
        self.outputpin = outputpin
        self.job_id = TransformationJob._job_id_counter + 1
        TransformationJob._job_id_counter += 1
        self.transformation = transformation
        self.semantic_cache = semantic_cache
        self.debug = debug
        self.python_debug = python_debug
        self.executor = None
        self.future = None
        self.remote = False
        self.restart = False
        self.n_restarted = 0

    async def _probe_remote(self, clients):
        if not len(clients):
            return
        coros = []
        for client in clients:
            coro = client.status(self.checksum)
            coros.append(coro)
        futures = [asyncio.ensure_future(coro) for coro in coros]
        rev = {fut:n for n,fut in enumerate(futures)}

        best_client = None
        best_status = None
        self.remote_result = None
        while 1:
            done, pending = await asyncio.wait(
                futures,
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            for fut in done:
                if fut.exception() is not None:
                    try:
                        fut.result()
                    except:
                        exc = traceback.format_exc()
                        print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                try:
                    result = "<unknown>"
                    result = fut.result()
                    status = result[0]
                    if status == 2:
                        status, _, _ = result
                    else:
                        status, response = result
                        if status == 0:
                            exception = response
                except:
                    print_debug("STATUS RESULT", result)
                    print_debug(traceback.format_exc())
                    continue
                if not isinstance(status, int):
                    continue
                if status < 0:
                    continue
                if best_status is None or status > best_status:
                    best_status = status
                    best_client = rev[fut]
                if status == 3:
                    self.remote = True
                    self.remote_status = 3
                    self.remote_clients = None
                    self.remote_result = response
                    for fut in pending:
                        fut.cancel()
                    return
            if not len(pending):
                #print("BEST STATUS", best_status)
                if best_status is None:
                    return
                self.remote = True
                if best_status == 0:
                    self.remote_status = 0
                    self.remote_result = exception
                    return
                if best_status == 1:
                    client = clients[best_client]
                    self.remote_status = best_status
                    self.remote_clients = [client]
                    return
                best_clients = []
                for n, fut in enumerate(futures):
                    if fut.exception() is not None:
                        continue
                    try:
                        status = fut.result()[0]
                    except:
                        continue
                    if status == best_status:
                        best_clients.append(clients[n])
                assert len(best_clients)
                self.remote_status = best_status
                self.remote_clients = best_clients
                break
        #print("PROBE DONE", self.remote_status)


    def execute(self, prelim_callback, progress_callback):
        coro = self._execute(prelim_callback, progress_callback)
        self.future = asyncio.ensure_future(coro)
        self.future.add_done_callback(
            functools.partial(
                transformation_cache.job_done,
                self
            )
        )

    async def _execute(self, prelim_callback, progress_callback):
        while not transformation_cache.active:
            await asyncio.sleep(0.05)
        clients = list(communion_client_manager.clients["transformation"])
        await self._probe_remote(clients)
        if self.remote and not self.debug and not self.python_debug:
            self.remote_futures = None
            try:
                result = await self._execute_remote(
                    prelim_callback, progress_callback
                )
                logs = None
            finally:
                self.remote_futures = None
        else:
            result, logs = await self._execute_local(
                prelim_callback, progress_callback
            )
        if self.restart:
            self.n_restarted += 1
            if self.n_restarted > 100:
                raise SeamlessTransformationError("Restarted transformation 100 times")
            self.restart = False
            result, logs = await self._execute(
                prelim_callback, progress_callback
            )
        return result, logs

    async def _execute_remote(self,
        prelim_callback, progress_callback
    ):

        async def get_result1(client):
            try:
                await client.submit(self.checksum)
                result = await client.status(self.checksum)
                return result
            except asyncio.CancelledError:
                if self._hard_cancelled:
                    await client.hard_cancel(self.checksum)
                raise

        async def get_result2(client):
            try:
                await client.wait(self.checksum)
                return await client.status(self.checksum)
            except asyncio.CancelledError:
                if self._hard_cancelled:
                    await client.hard_cancel(self.checksum)
                elif self._cancelled:
                    await client.cancel(self.checksum)
                raise

        if self.remote_status == 3:
            result_checksum = self.remote_result
            return result_checksum
        if self.remote_status == 0:
            exc_str = self.remote_result
            raise RemoteJobError(exc_str)
        elif self.remote_status == 1:
            get_result = get_result1
        elif self.remote_status == 2:
            get_result = get_result2
        else:
            raise ValueError(self.remote_status)
        clients = self.remote_clients
        assert len(clients)

        futures = []
        self.remote_futures = futures
        rev = {}
        for n, client in enumerate(clients):
            future = asyncio.ensure_future(get_result(client))
            futures.append(future)
            rev[future] = n

        has_exceptions = False
        has_negative_status = False
        while 1:
            done, pending = await asyncio.wait(
                futures,
                timeout=REMOTE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED
            )
            go_on = (len(pending) > 0)
            status = None
            for future in done:
                if future.exception() is not None:
                    try:
                        future.result()
                    except:
                        exc = traceback.format_exc()
                        print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                try:
                    result = future.result()
                    status = result[0]
                except:
                    exc = traceback.format_exc()
                    print_debug("Transformation {}: {}".format(self.checksum.hex(), exc))
                    continue
                if not isinstance(status, int):
                    continue
                if status == 0:
                    has_exceptions = True
                    exc_str = result[1]
                elif status < 0:
                    has_negative_status = True
                elif status not in (2, 3): # erroneous behaviour
                    continue
                elif status == 2:
                    _, progress, prelim_checksum = result
                    progress_callback(self, progress)
                    prelim_callback(self, prelim_checksum)
                    n = rev.pop(future)
                    futures.remove(future)
                    client = clients[n]
                    get_result = get_result2
                    new_future = asyncio.ensure_future(get_result(client))
                    rev[new_future] = n
                    futures.append(new_future)
                    go_on = True
                    continue
                else: # status == 3
                    _, response = result
                    return response
            if not go_on:
                break
        if status == 1 and get_result is get_result1:
            self.restart = True
            return
        elif has_negative_status and not has_exceptions:
            self.restart = True
            self.remote = False
        elif has_exceptions:
            raise RemoteJobError(exc_str)
        else:
            raise RemoteJobError()


    async def _execute_local(self,
        prelim_callback, progress_callback
    ):
        with_ipython_kernel = False
        env = self.transformation.get("__env__")
        if env is not None:
            env = get_buffer(env)
            env = json.loads(env.decode())
            assert env is not None
            validate_environment(env)
            if "powers" in env and "ipython" in env["powers"]:
                with_ipython_kernel = True
        values = {}
        namespace = {
            "__name__": "transformer",
            "__package__": "transformer",
        }
        inputs = []
        code = None
        logs = [None, None]
        lock = await acquire_lock(self.checksum)
        namespace["PINS"] = {}
        modules_to_build = {}
        for pinname in sorted(self.transformation.keys()):
            if pinname in ("__compilers__", "__languages__"):
                continue
            if pinname == "__output__":
                continue
            if pinname == "__env__":
                continue
            celltype, subcelltype, sem_checksum = self.transformation[pinname]
            if syntactic_is_semantic(celltype, subcelltype):
                checksum = sem_checksum
            else:
                # For now, assume that the first syntactic checksum gives a value
                semkey = sem_checksum, celltype, subcelltype
                checksum = self.semantic_cache[semkey][0]
            if checksum is None:
                values[pinname] = None
                continue
            # fingertipping must have happened before
            buffer = get_buffer(checksum)
            assert buffer is not None
            try:
                value = await deserialize(buffer, checksum, celltype, False)
            except Exception as exc:
                e = traceback.format_exc()
                raise Exception(pinname, e) from None
            if value is None:
                raise CacheMissError(pinname, self.codename)
            if pinname == "code":
                code = value
            elif (celltype, subcelltype) == ("plain", "module"):
                modules_to_build[pinname] = value
            else:
                namespace["PINS"][pinname] = value
                namespace[pinname] = value
                inputs.append(pinname)
        for pinname in self.transformation:
            if pinname in ("__output__", "__env__", "__compilers__", "__languages__"):
                continue
            celltype, _, _ = self.transformation[pinname]
            if celltype != "mixed":
                continue
            schema_pinname = pinname + "_SCHEMA"
            schema_pin = self.transformation.get(schema_pinname)
            schema = None
            if schema_pin is not None:
                schema_celltype, _, _ = schema_pin
                assert schema_celltype == "plain", schema_pinname
                schema = namespace[schema_pinname]
            if schema is None and isinstance(namespace[pinname], Scalar):
                continue
            if schema is None:
                schema = {}
            v = Silk(
                data=namespace[pinname],
                schema=schema
            )
            namespace["PINS"][pinname] = v
            namespace[pinname] = v

        module_workspace = {}
        compilers = self.transformation.get("__compilers__", default_compilers)
        languages = self.transformation.get("__languages__", default_languages)
        build_all_modules(
            modules_to_build, module_workspace,
            compilers=compilers, languages=languages
        )
        assert code is not None

        async def get_result_checksum(result_buffer):
            if result_buffer is None:
                return None
            try:
                await validate_subcelltype(
                    result_buffer, celltype, subcelltype,
                    self.codename
                )
                result_checksum = await calculate_checksum(result_buffer)
            except Exception:
                raise SeamlessInvalidValueError(result)
            return result_checksum

        self.start = time.time()
        running = False
        try:
            queue = Queue()
            outputname, celltype, subcelltype = self.outputpin
            args = (
                self.codename, code,
                with_ipython_kernel,
                injector, module_workspace,
                self.codename,
                namespace, inputs, outputname, celltype, queue,                
            )
            kwargs = {"python_debug": self.python_debug}
            execute_command = execute_debug if self.debug else execute
            self.executor = Process(target=execute_command,args=args, kwargs=kwargs, daemon=True)
            self.executor.start()
            running = True
            result = None
            done = False
            while 1:
                prelim = None
                while not queue.empty():
                    status, msg = queue.get()
                    queue.task_done()
                    if status == 0:
                        result_buffer = msg
                        done = True
                        break
                    elif status == 1:
                        raise SeamlessTransformationError(msg)
                    elif status == 2:
                        prelim_buffer = msg
                        prelim_checksum = await get_result_checksum(prelim_buffer)
                        buffer_cache.cache_buffer(prelim_checksum, prelim_buffer)
                        prelim_callback(self, prelim_checksum)
                    elif status == 3:
                        progress = msg
                        progress_callback(self, progress)
                    elif status == 4:
                        is_stderr, content = msg
                        try:
                            content = str(content)
                        except:
                            pass
                        else:
                            if len(content) > 10000:
                                skipped = len(content)-5000-4960
                                content2 = content[:4960]
                                content2 += "\n...(skipped %d characters)...\n" % skipped
                                content2 += content[-5000:]
                                content = content2
                            logs[is_stderr] = content
                    else:
                        raise Exception("Unknown return status {}".format(status))
                if not self.executor.is_alive():
                    if self.executor.exitcode != 0:
                        raise SeamlessTransformationError(
                          "Transformation exited with code %s\n" % self.executor.exitcode
                        )
                    if not done:
                        raise SeamlessTransformationError("Transformation exited without result")
                if done:
                    break
                await asyncio.sleep(0.01)
            if not self.executor.is_alive():
                self.executor = None
        except asyncio.CancelledError:
            if running:
                self.executor.terminate()
                forked_processes[self.executor] = time.time()
            raise asyncio.CancelledError from None
        finally:
            release_lock(lock)
        result_checksum = await get_result_checksum(result_buffer)
        buffer_cache.cache_buffer(result_checksum, result_buffer)

        if logs[0] is None and logs[1] is None:
            logstr = None
        elif logs[0] is not None and logs[1] is None:
            logstr = logs[0]
        elif logs[0] is None and logs[1] is not None:
            logstr = logs[1]
        else:
            logstr = """*************************************************
* Standard output
*************************************************
{}
*************************************************
*************************************************
* Standard error
*************************************************
{}
""".format(logs[0], logs[1])
        return result_checksum, logstr



from .protocol.get_buffer import get_buffer
from .protocol.deserialize import deserialize
from .protocol.serialize import serialize
from .protocol.calculate_checksum import calculate_checksum
from .protocol.validate_subcelltype import validate_subcelltype
from .cache import CacheMissError
from .cache.buffer_cache import buffer_cache
from .cache.transformation_cache import transformation_cache, syntactic_is_semantic
from .status import SeamlessInvalidValueError
from silk import Silk, Scalar
from ..communion_client import communion_client_manager
from .environment import validate_environment
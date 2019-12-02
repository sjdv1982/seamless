"""Schedules asynchronous (transformer) jobs"""
import weakref
import asyncio
import multiprocessing
import sys
import traceback
import functools
import time

from .execute import Queue, Executor, execute, execute_debug
from .run_multi_remote import run_multi_remote, run_multi_remote_pair
from .injector import transformer_injector as injector
from .build_module import build_module_async

DEBUG = True

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
        raise Exception("Local computation has been disabled for this Seamless instance")
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

class RemoteJobError(Exception):
    def __str__(self):
        return self.__class__.__name__

###############################################################################

class TransformationJob:
    _job_id_counter = 0
    _cancelled = False
    _hard_cancelled = False
    remote_futures = None
    start = None
    def __init__(self,
        checksum, codename,
        buffer_cache, transformation, 
        semantic_cache, debug
    ):
        self.checksum = checksum
        assert codename is not None
        self.codename = codename        
        assert "code" in transformation, transformation.keys()
        for pinname in transformation:
            if pinname != "__output__":
                assert transformation[pinname][2] is not None, pinname
        outputpin = transformation["__output__"]
        outputname, celltype, subcelltype = outputpin        
        self.outputpin = outputpin
        self.buffer_cache = weakref.ref(buffer_cache)
        self.job_id = TransformationJob._job_id_counter + 1
        TransformationJob._job_id_counter += 1
        self.transformation = transformation
        self.semantic_cache = semantic_cache
        self.debug = debug
        self.executor = None
        self.future = None
        self.remote = False
        self.restart = False
    

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
                    continue
                try:
                    result = "<unknown>"
                    result = fut.result()
                    status = result[0]
                    if status == 2:
                        status, _, _ = result
                    else:
                        status, response = result
                except:
                    if DEBUG:
                        print("STATUS RESULT", result)
                        traceback.print_exc()
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
        if self.remote: 
            self.remote_futures = None
            try:
                result = await self._execute_remote(
                    prelim_callback, progress_callback
                )
            finally:
                self.remote_futures = None
        else:
            result = await self._execute_local(
                prelim_callback, progress_callback
            )
        if self.restart:
            self.restart = False
            self.remote = False
            result = await self._execute(
                prelim_callback, progress_callback
            )
        return result

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
            raise RemoteJobError()
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
            for future in done:
                if future.exception() is not None:
                    if DEBUG:
                        try:
                            future.result()
                        except:
                            traceback.print_exc()
                    continue
                try:
                    result = future.result()
                    status = result[0]
                except:
                    if DEBUG:
                        traceback.print_exc()
                    continue
                #print("REMOTE RESULT:", status, response)
                if not isinstance(status, int):
                    continue
                if status == 0:
                    has_exceptions = True                    
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
                    new_future = asyncio.ensure_future(get_result2(client))
                    rev[new_future] = n
                    futures.append(new_future)
                    go_on = True                    
                    continue
                else: # status == 3
                    _, response = result
                    return response
            if not go_on:
                break
        if has_negative_status and not has_exceptions:
            self.restart = True
        else:            
            raise RemoteJobError()

    async def _execute_local(self, 
        prelim_callback, progress_callback
    ):
        buffer_cache = self.buffer_cache()
        values = {}
        module_workspace = {}
        namespace = {"__name__": "transformer"}
        inputs = []
        code = None
        for pinname in self.transformation:
            if pinname == "__output__":
                continue
            celltype, subcelltype, sem_checksum = self.transformation[pinname]
            if syntactic_is_semantic(celltype, subcelltype):
                checksum = sem_checksum
            else:
                # For now, assume that the first syntactic checksum gives a value
                checksum = self.semantic_cache[sem_checksum][0]
            if checksum is None:
                values[pinname] = None
                continue
            buffer = await get_buffer(checksum, buffer_cache)            
            assert buffer is not None
            value = await deserialize(buffer, checksum, celltype, False)
            if value is None:
                raise CacheMissError(pinname, self.codename)
            if pinname == "code":
                code = value
            elif (celltype, subcelltype) == ("plain", "module"):
                mod = await build_module_async(value)
                assert mod is not None # build_module_async failed
                module_workspace[pinname] = mod[1]
            else:
                namespace[pinname] = value
                inputs.append(pinname)
        for pinname in self.transformation:
            if pinname == "__output__":
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
            namespace[pinname] = v

        assert code is not None

        async def get_result_checksum(result):
            if result is None:
                return None
            try:
                await validate_subcelltype(
                    result, celltype, subcelltype, 
                    self.codename, buffer_cache
                )
                result_checksum = await calculate_checksum(result)
            except Exception:
                raise SeamlessInvalidValueError(result)
            return result_checksum

        lock = await acquire_lock(self.checksum)
        self.start = time.time()
        running = False        
        try:                        
            queue = Queue()
            outputname, celltype, subcelltype = self.outputpin
            args = (
                self.codename, code,
                injector, module_workspace,
                self.codename,
                namespace, inputs, outputname, celltype, queue
            )            
            execute_command = execute_debug if self.debug else execute 
            self.executor = Executor(target=execute_command,args=args, daemon=True)
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
                        result = msg
                        done = True
                        break
                    elif status == 1:
                        raise Exception(msg)
                    elif status == 2:
                        prelim = msg
                        prelim_checksum = await get_result_checksum(prelim)
                        prelim_callback(self, prelim_checksum)
                    elif status == 3:
                        progress = msg                        
                        progress_callback(self, progress)
                if not self.executor.is_alive():
                    done = True
                if done:
                    break
                await asyncio.sleep(0.001)
            if not self.executor.is_alive():
                self.executor = None
        except asyncio.CancelledError:
            if running:
                self.executor.terminate()
        finally:            
            release_lock(lock)
        result_checksum = await get_result_checksum(result)
        return result_checksum
                


from .protocol.get_buffer import get_buffer
from .protocol.deserialize import deserialize
from .protocol.serialize import serialize
from .protocol.calculate_checksum import calculate_checksum
from .protocol.validate_subcelltype import validate_subcelltype
from .cache import CacheMissError
from .cache.transformation_cache import transformation_cache, syntactic_is_semantic
from .status import SeamlessInvalidValueError
from ..silk import Silk, Scalar
from ..communion_client import communion_client_manager
"""Schedules asynchronous (transformer) jobs"""
import weakref
import asyncio
import multiprocessing
import sys
import traceback

from .execute import Queue, Executor, execute, execute_debug
from .run_multi_remote import run_multi_remote, run_multi_remote_pair
from .injector import transformer_injector as injector
from .build_module import build_module

###############################################################################
# Local jobs
###############################################################################

_locks = [False] * multiprocessing.cpu_count()

def set_ncores(ncores):
    if len(_locks) != ncores:
        if any(_locks):
            msg = "WARNING: Cannot change ncores from %d to %d since there are running jobs"
            print(msg % (len(_locks), ncores), file=sys.stderr)
        else:
            _locks[:] = [False] * ncores

async def acquire_lock():
    if not len(_locks):
        raise Exception("Local computation has been disabled for this Seamless instance")
    while 1:        
        for locknr, lock in enumerate(_locks):
            if lock == False:
                _locks[locknr] = True
                return locknr                
        await asyncio.sleep(0.01)

def release_lock(locknr):
    assert _locks[locknr] == True
    _locks[locknr] = False

###############################################################################
# Remote jobs
###############################################################################

remote_job_servers = []

async def run_remote_job(*args, **kwargs):
    raise NotImplementedError # livegraph branch
    # use transformer_job_run; run_multi_remote_pair?
"""
async def run_remote_job(level1, origin=None):
    from .cache.transform_cache import TransformerLevel1
    content = level1.serialize()
    validate_content = TransformerLevel1.deserialize(content).serialize()    
    assert content == validate_content, (content, "\n", validate_content)
    future = run_multi_remote_pair(remote_job_servers, content, origin)
    result = await future
    return result
"""

class TransformationJob:
    _job_id_counter = 0
    def __init__(self, 
        buffer_cache, transformation, 
        semantic_cache, debug
    ):
        assert "code" in transformation, transformation.keys()
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
        self.codename = None
        self.future = None

    def execute(self, codename):
        # TODO: use communion "transformer_job_check" to find a remote server
        # run_multi_remote_pair?
        remote = False ###
        if remote: 
            awaitable = run_remote_job(NotImplemented)
        else:
            awaitable = self._execute_local(codename)
        self.future = asyncio.ensure_future(awaitable)

    async def _execute_local(self, codename):
        self.codename = codename
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
            buffer = await get_buffer_async(checksum, buffer_cache)
            assert buffer is not None
            value = await deserialize(buffer, checksum, celltype, False)
            if value is None:
                raise CacheMissError(pinname, codename)
            if pinname == "code":
                code = value
            elif (celltype, subcelltype) == ("plain", "module"):
                mod = await build_module_async(value)
                module_workspace[pinname] = mod[1]
            else:
                namespace[pinname] = value
                inputs.append(pinname)
        assert code is not None

        lock = await acquire_lock()
        running = False
        try:                        
            queue = Queue()
            outputname, celltype, subcelltype = self.outputpin
            args = (
                codename, code,
                injector, module_workspace,
                codename,
                namespace, inputs, outputname, queue
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
                    if status == -1:
                        prelim = msg
                    elif status == 0:
                        result = msg
                        done = True
                        break
                    elif status == 1:
                        raise Exception(msg)
                if not self.executor.is_alive():
                    done = True
                if done:
                    break
                if prelim is not None:
                    raise NotImplementedError # livegraph branch
                await asyncio.sleep(0)
            if not self.executor.is_alive():
                self.executor = None
        except asyncio.CancelledError:
            if running:
                self.executor.terminate()
        finally:            
            release_lock(lock)
        if result is not None:
            try:
                result_buffer = await serialize(result, celltype)
                await validate_subcelltype(
                    result_buffer, celltype, subcelltype, 
                    codename, buffer_cache
                )
                result_checksum = await calculate_checksum(result_buffer)
            except Exception:
                raise SeamlessInvalidValueError(result)
            #print("RESULT", result, result_buffer, result_checksum)
        return result_checksum
                


from .protocol.get_buffer import get_buffer_async
from .protocol.deserialize import deserialize
from .protocol.serialize import serialize
from .protocol.calculate_checksum import calculate_checksum
from .protocol.validate_subcelltype import validate_subcelltype
from .cache import CacheMissError
from .cache.transformation_cache import syntactic_is_semantic
from .status import SeamlessInvalidValueError
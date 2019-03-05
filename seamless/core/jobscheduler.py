"""Schedules asynchronous (transformer) jobs"""
import weakref
import asyncio
import multiprocessing
import sys
import traceback

from .execute import Queue, Executor, execute ### TODO: also use execute_debug
from .run_multi_remote import run_multi_remote, run_multi_remote_pair

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

async def run_remote_job(level1, origin=None):
    from .cache.transform_cache import TransformerLevel1
    content = level1.serialize()
    validate_content = TransformerLevel1.deserialize(content).serialize()    
    assert content == validate_content, (content, "\n", validate_content)
    future = run_multi_remote_pair(remote_job_servers, content, origin)
    result = await future
    return result

###############################################################################

class JobScheduler:
    _id = 0
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.jobs = {} #hash(level2)-to-job
        self.remote_jobs = {} #hash(level1)-to-job

    @classmethod
    def new_id(cls):
        cls._id += 1
        return cls._id

    def schedule_remote(self, level1, count):
        hlevel1 = level1.get_hash()
        if count < 0:
            count = -count
            if hlevel1 not in self.remote_jobs:
                return None
            job = self.remote_jobs[hlevel1]
            assert job.count >= count
            job.count -= count
            if job.count == 0:
                job.cancel()
                self.remote_jobs.pop(hlevel1)
                return None
            return job
        if hlevel1 in self.remote_jobs:
            job = self.jobs[hlevel1]
            job.count += count
            return job
        if not len(remote_job_servers):
            return None
        tcache = self.manager().transform_cache
        job = Job(self, level1, None, remote=True)
        job.count = count
        self.remote_jobs[hlevel1] = job
        transformer = tcache.transformer_from_hlevel1.get(hlevel1)
        if transformer is None:
            return None
        job.execute(transformer)
        return job

    def schedule(self, level2, count, transformer_can_be_none):
        hlevel2 = level2.get_hash()
        if count < 0:
            count = -count
            assert hlevel2 in self.jobs
            job = self.jobs[hlevel2]
            assert job.count >= count
            job.count -= count
            if job.count == 0:
                job.cancel()
                self.jobs.pop(hlevel2)
                return None
            return job
        if hlevel2 in self.jobs:
            job = self.jobs[hlevel2]
            job.count += count
            return job
        tcache = self.manager().transform_cache
        hlevel1 = tcache.hlevel1_from_hlevel2[hlevel2]
        level1 = tcache.revhash_hlevel1[hlevel1]
        job = Job(self, level1, level2, remote=False)
        job.count = count
        self.jobs[hlevel2] = job
        transformer = tcache.transformer_from_hlevel1.get(hlevel1)
        if transformer is None and not transformer_can_be_none: # Transformer must have been overruled...
            return None
        job.execute(transformer)
        return job

    def jobarray(self, jobs):
        if len(jobs):
            assert jobs[0].scheduler() is self
        return JobArray(jobs)

    def cleanup(self):
        manager = self.manager()
        for jobs in (self.jobs, self.remote_jobs):
            toclean = []
            for key, job in jobs.items():                
                future = job.future
                ft = future.done() if future else None                
                if future is None:
                    toclean.append(key)
                else:
                    if future.done():
                        toclean.append(key)
                        exception = future.exception()
                        if exception is not None:
                            try:
                                manager.set_transformer_result_exception(job.level1, job.level2, exception)
                            except:
                                traceback.print_exc()
                        toclean.append(key)
            for key in toclean:
                jobs.pop(key, None)

class Job:
    def __init__(self, scheduler, level1, level2, remote):
        self.scheduler = weakref.ref(scheduler)
        self.job_id = scheduler.new_id()
        self.level1 = level1
        self.level2 = level2
        self.remote = remote
        self.executor = None
        self.future = None

    async def _execute(self, transformer):
        # transformer arg is just for tracebacks
        if self.remote: 
            await self._execute_remote()
        else:
            await self._execute_local(transformer)

    async def _execute_remote(self):
        manager = self.scheduler().manager()
        try:
            result = await run_remote_job(self.level1)
            if result is not None:
                manager.set_transformer_result(self.level1, self.level2, None, result, prelim=False)
            else:
                # TODO: store exception! is not printed in run_multi_remote_pair...
                raise Exception("Remote job execution failed")
        finally:
            self.future = None
            self.scheduler().cleanup() # maybe a bit overkill, but better safe than sorry            

    async def _execute_local(self, transformer):
        # transformer arg is just for tracebacks
        print("Execute local")
        lock = await acquire_lock()
        try:
            transformer_path = transformer._format_path()
        except:
            transformer_path = "<Unknown transformer>"
        manager = self.scheduler().manager()
        try:            
            namespace = {}
            queue = Queue()
            inputs = []
            assert "code" in self.level2, list(self.level2._expressions.keys())            
            for pin in self.level2:
                semantic_key = self.level2[pin]
                value = manager.value_cache.get_object(semantic_key)
                if pin == "code":
                    code = value
                else:
                    if semantic_key.access_mode in ("mixed", "default"):
                        if value is not None:
                            value = value[2]
                    namespace[pin] = value
                    inputs.append(pin)
            args = (
                transformer_path, code,
                str(transformer),
                namespace, inputs, self.level2.output_name, queue
            )            
            self.executor = Executor(target=execute,args=args, daemon=True)
            self.executor.start()
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
                    manager.set_transformer_result(self.level1, self.level2, prelim, None, prelim=True)
                await asyncio.sleep(0.01)
            if not self.executor.is_alive():
                self.executor = None            
            manager.set_transformer_result(self.level1, self.level2, result, None, prelim=False)
        except Exception as exception:
            manager.set_transformer_result_exception(self.level1, self.level2, exception)
        finally:            
            self.future = None
            self.scheduler().cleanup() # maybe a bit overkill, but better safe than sorry            
            release_lock(lock)

    def execute(self, transformer):
        assert self.future is None
        #print("EXECUTE", transformer)
        self.future = asyncio.ensure_future(self._execute(transformer))
        
    def cancel(self):
        if self.remote: raise NotImplementedError  ### cache branch
        #print("CANCEL", self.transformer)
        assert self.executor is not None
        self.executor.terminate()


class JobArray:
    def __init__(self, jobs):
        self.jobs = jobs
        for job in jobs:
            assert isinstance(job, Job)
            assert job.scheduler() is jobs[0].scheduler()
        futures = [job.future for job in jobs]
        self.future = asyncio.ensure_future(
            asyncio.gather(*futures, return_exceptions=True)
        )
        
    def cancel(self):
        for job in self.jobs:
            job.cancel()

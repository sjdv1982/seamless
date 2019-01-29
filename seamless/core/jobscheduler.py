"""Schedules asynchronous (transformer) jobs"""
import weakref
import asyncio

from .localjob import Queue, Executor, execute ### TODO: also use execute_debug

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
        hlevel1 = hash(level1)
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
            job = self.jobs[hlevel2]
            job.count += count
            return job
        # TODO: create remote job if a server has been registered
        return None ###
        '''
        tcache = self.manager().transform_cache
        job = Job(self, level1, None, remote=True)
        job.count = count
        self.remote_jobs[hlevel1] = job
        transformer = tcache.transformer_from_hlevel1[hlevel1]
        job.execute(transformer)
        return True
        '''


    def schedule(self, level2, count):
        hlevel2 = hash(level2)
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
        hlevel1 = tcache.hlevel2_from_hlevel1[hlevel2]
        level1 = tcache.revhash_hlevel1[hlevel1]
        job = Job(self, level1, level2, remote=False)
        job.count = count
        self.jobs[hlevel2] = job
        transformer = tcache.transformer_from_hlevel1[hlevel1]
        job.execute(transformer)
        return job


class Job:
    def __init__(self, scheduler, level1, level2, remote):
        self.scheduler = weakref.ref(scheduler)
        self.job_id = scheduler.new_id()
        self.level1 = level1
        self.level2 = level2
        self.remote = remote
        self.executor = None
        self.future = None
        if remote: raise NotImplementedError  ### cache branch

    async def _execute(self, transformer):
        # transformer is just for tracebacks
        if self.remote: raise NotImplementedError  ### cache branch
        manager = self.scheduler().manager()
        namespace = {}
        queue = Queue()
        assert "code" in self.level2, list(self.level2._expressions.keys())
        for pin in self.level2:
            semantic_key = self.level2[pin]
            value = manager.value_cache.get_object(semantic_key)
            if pin == "code":
                code = value
            else:
                namespace[pin] = value
        args = (
            transformer._format_path(), code,
            str(transformer),
            namespace, self.level2.output_name, queue
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
                    print("TODO: jobscheduler: set Manager.status[transformer].exec='ERR'")
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
        if result is not None:
            manager.set_transformer_result(self.level1, self.level2, result, None, prelim=False)
        self.future = None

    def execute(self, transformer):
        assert self.future is None
        print("EXECUTE", transformer)
        self.future = asyncio.ensure_future(self._execute(transformer))
        
    def cancel(self):
        if self.remote: raise NotImplementedError  ### cache branch
        print("CANCEL", self.transformer)
        assert self.executor is not None
        self.executor.terminate()

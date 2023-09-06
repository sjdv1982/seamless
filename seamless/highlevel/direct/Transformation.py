import asyncio
import traceback

class Transformation:
    _future = None
    
    def __init__(self,
        result_celltype,
        resolver_sync,
        resolver_async,
        evaluator_sync,
        evaluator_async,
        upstream_dependencies:dict[str, "Transformation"]={}
    ):                 
        self._result_celltype = result_celltype
        self._upstream_dependencies = upstream_dependencies.copy()
        self._resolver_sync = resolver_sync
        self._resolver_async = resolver_async
        self._transformation_checksum = None
        self._resolved = False

        self._evaluator_sync = evaluator_sync
        self._evaluator_async = evaluator_async        
        self._result_checksum = None
        self._evaluated = False
        self._exception = None

    def _resolve_sync(self):
        if self._resolved:
            return
        try:
            tf_checksum = self._resolver_sync()
            if tf_checksum is None:
                raise ValueError("Cannot obtain transformation checksum")
            self._transformation_checksum = tf_checksum
        except Exception:
            self._exception = traceback.format_exc()
        finally:
            self._resolved = True

    async def _resolve_async(self):
        if self._resolved:
            return
        try:
            tf_checksum = await self._resolver_async()
            if tf_checksum is None:
                raise ValueError("Cannot obtain transformation checksum")
            self._transformation_checksum = tf_checksum
        except Exception:
            self._exception = traceback.format_exc()
        finally:
            self._resolved = True

    def _evaluate_sync(self):
        if self._evaluated:
            return
        self._resolve_sync()
        if self._exception is not None:
            return
        try:
            result_checksum = self._evaluator_sync()
            if result_checksum is None:
                raise ValueError("Result is empty")
            self._result_checksum = result_checksum
        except Exception:
            self._exception = traceback.format_exc()
        finally:
            self._evaluated = True

    async def _evaluate_async(self):
        if self._evaluated:
            return
        await self._resolve_async()
        if self._exception is not None:
            return
        try:
            result_checksum = await self._evaluator_async()
            if result_checksum is None:
                raise ValueError("Result is empty")
            self._result_checksum = result_checksum
        except Exception:
            self._exception = traceback.format_exc()
        finally:
            self._evaluated = True

    def _run_dependencies(self):
        for depname, dep in self._upstream_dependencies:
            dep.start()
        for depname, dep in self._upstream_dependencies:
            dep.compute()
            if dep.exception is not None:
                msg = "Dependency '{}' has an exception: {}"
                raise RuntimeError(msg.format(depname, dep.exception))

    async def _run_dependencies_async(self):
        tasks = {}
        for depname, dep in self._upstream_dependencies:
            tasks[depname] = asyncio.get_event_loop().create_task(dep.computation())
        await asyncio.gather(tasks.values(), return_exceptions=True)
        for depname, task in tasks:
            dep = self._upstream_dependencies[depname]
            if dep.exception is not None:
                msg = "Dependency '{}' has an exception: {}"
                raise RuntimeError(msg.format(depname, dep.exception))

    def compute(self):
        self._run_dependencies()
        self._evaluate_sync()
        if self._future is not None:
            self._future.cancel() # redundant
            self._future = None

    async def computation(self):
        if self._future is not None:
            await self._future
            self._future = None
        else:
            await self._run_dependencies_async()
            await self._evaluate_async()

    def start(self):
        if self._future is not None:
            return
        self._future = asyncio.get_event_loop().create_task(self.computation())

    def as_checksum(self):
        from .. import Checksum
        self._resolve_sync()
        return Checksum(self._transformation_checksum)

    def as_dict(self):
        from seamless import CacheMissError
        from ...core.protocol.get_buffer import get_buffer
        from ...core.protocol.deserialize import deserialize_sync
        tf_checksum = self._transformation_checksum
        if tf_checksum is None:
            return None
        buf = get_buffer(tf_checksum, remote=True)
        if buf is None:
            raise CacheMissError(tf_checksum)
        return deserialize_sync(buf, tf_checksum, "plain", copy=True)
        
    @property
    def checksum(self):
        from .. import Checksum
        return Checksum(self._result_checksum)

    @property
    def buffer(self):
        from seamless import CacheMissError
        from ...core.protocol.get_buffer import get_buffer
        result_checksum = self.checksum
        if result_checksum.value is None:
            return None
        buf = get_buffer(result_checksum.bytes(), remote=True)
        if buf is None:
            raise CacheMissError(result_checksum)
        return buf

    @property
    def value(self):
        from ...core.protocol.deserialize import deserialize_sync
        if self.checksum is None:
            return None
        buf = self.buffer
        if buf is None:
            return None
        return deserialize_sync(self.buffer, self.checksum.bytes(), self.celltype, copy=True)

    @property
    def celltype(self):
        return self._result_celltype

    @property
    def exception(self):        
        return self._exception

    @property
    def logs(self):
        from ...core.cache.transformation_cache import transformation_cache
        checksum = self.as_checksum().bytes()
        if checksum is None:
            return None
        logs = transformation_cache.transformation_logs.get(checksum)
        if logs is not None:
            return logs

    def clear_exception(self):
        self._exception = None
        if self._resolved and self._transformation_checksum is None:
            self._resolved = False
        elif self._evaluated and self._result_checksum is None:
            self._evaluated = False


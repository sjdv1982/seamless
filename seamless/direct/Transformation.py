"""Transformation class, to run transformations by interacting with seamless.workflow.core"""

import asyncio
from copy import deepcopy
import traceback

from seamless import Checksum, CacheMissError
from seamless.util.transformation import tf_get_buffer
from seamless.checksum.get_buffer import get_buffer
from seamless.checksum.deserialize import deserialize_sync, deserialize


class Transformation:
    """Transformation class, to run transformations by interacting with seamless.workflow.core"""

    _future = None

    def __init__(
        self,
        result_celltype,
        resolver_sync,
        resolver_async,
        evaluator_sync,
        evaluator_async,
        upstream_dependencies: dict[str, "Transformation"] = None,
        *,
        meta=None
    ):
        self._result_celltype = result_celltype
        if upstream_dependencies is None:
            upstream_dependencies = {}
        self._upstream_dependencies = upstream_dependencies.copy()
        self._resolver_sync = resolver_sync
        self._resolver_async = resolver_async
        self._transformation_checksum = None
        self._resolved = False
        self._scratch = False

        self._evaluator_sync = evaluator_sync
        self._evaluator_async = evaluator_async
        self._result_checksum = None
        self._evaluated = False
        self._exception = None
        self._meta = meta

    @property
    def scratch(self) -> bool:
        """If True, the transformation result buffer will not be saved."""
        return self._scratch

    @scratch.setter
    def scratch(self, value: bool):
        self._scratch = value

    def _resolve_sync(self):
        if self._resolved:
            return
        try:
            tf_checksum = self._resolver_sync(self)
            tf_checksum = Checksum(tf_checksum)
            if not tf_checksum:
                raise ValueError("Cannot obtain transformation checksum")
            self._transformation_checksum = tf_checksum
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"
        finally:
            self._resolved = True

    async def _resolve_async(self):
        if self._resolved:
            return
        try:
            tf_checksum = await self._resolver_async(self)
            tf_checksum = Checksum(tf_checksum)
            if not tf_checksum:
                raise ValueError("Cannot obtain transformation checksum")
            self._transformation_checksum = tf_checksum
        except AssertionError:
            self._exception = traceback.format_exc().strip("\n") + "\n"
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"
        finally:
            self._resolved = True

    def _evaluate_sync(self):
        if self._evaluated:
            return
        self._resolve_sync()
        if self._exception is not None:
            return
        try:
            result_checksum = self._evaluator_sync(self)
            result_checksum = Checksum(result_checksum)
            if not result_checksum:
                raise ValueError("Result is empty")
            self._result_checksum = result_checksum
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"
        finally:
            self._evaluated = True

    async def _evaluate_async(self):

        if self._evaluated:
            return
        await self._resolve_async()
        if self._exception is not None:
            return
        try:
            result_checksum = await self._evaluator_async(self)
            result_checksum = Checksum(result_checksum)
            if not result_checksum:
                raise ValueError("Result is empty")
            self._result_checksum = result_checksum
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"
        finally:
            self._evaluated = True

    def _run_dependencies(self):
        try:
            self.start()
            for depname, dep in self._upstream_dependencies.items():
                dep.compute()
                if dep.exception is not None:
                    msg = "Dependency '{}' has an exception:\n{}"
                    raise RuntimeError(msg.format(depname, dep.exception))
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"

    async def _run_dependencies_async(self):
        tasks = {}
        for depname, dep in self._upstream_dependencies.items():
            tasks[depname] = asyncio.get_event_loop().create_task(dep.computation())
        if len(tasks):
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        for depname, task in tasks.items():
            self._future_cleanup(task)
        try:
            for depname, _ in tasks.items():
                dep = self._upstream_dependencies[depname]
                if dep.exception is not None:
                    msg = "Dependency '{}' has an exception:\n{}"
                    raise RuntimeError(msg.format(depname, dep.exception))
        except Exception:
            self._exception = traceback.format_exc(limit=0).strip("\n") + "\n"

    @property
    def meta(self):
        """Transformation metadata"""
        return self._meta

    @meta.setter
    def meta(self, meta):
        self._meta.update(meta)
        for k in list(self._meta.keys()):
            if self._meta[k] is None:
                self._meta.pop(k)
        return self._meta

    def compute(self):
        """Compute the transformation synchronously"""
        if self._evaluated:
            return
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            self.start()
            loop.run_until_complete(self._future)
        else:
            self._run_dependencies()
            if self._exception is None:
                self._evaluate_sync()
            if self._future is not None:
                self._future.cancel()  # redundant
                self._future = None
        return self

    async def _computation(self):
        await self._run_dependencies_async()
        if self._exception is None:
            await self._evaluate_async()
        return self

    async def computation(self):
        """Compute the transformation asynchronously"""
        if self._future is not None:
            await self._future
        else:
            await self._computation()
        return self

    def _future_cleanup(self, fut):
        # to avoid "Task exception was never retrieved" messages
        try:
            fut.result()
        except asyncio.exceptions.CancelledError:
            pass
        except Exception:
            pass

    def start(self):
        """Starts the transformation computation synchronously"""
        for _depname, dep in self._upstream_dependencies.items():
            dep.start()
        if self._future is not None:
            return
        self._future = asyncio.get_event_loop().create_task(self._computation())
        self._future.add_done_callback(self._future_cleanup)

    def as_checksum(self):
        """Return the checksum of the transformation dict"""
        self._resolve_sync()
        return Checksum(self._transformation_checksum)

    def as_dict(self):
        """Return the transformation as a dict"""
        self._resolve_sync()
        tf_checksum = self._transformation_checksum
        tf_checksum = Checksum(tf_checksum)
        if not tf_checksum:
            return None
        buf = get_buffer(tf_checksum, remote=True)
        if buf is None:
            raise CacheMissError(tf_checksum.hex())
        return deserialize_sync(buf, tf_checksum, "plain", copy=True)

    @property
    def checksum(self) -> Checksum:
        """Get the result checksum of the transformation, if known."""

        return Checksum(self._result_checksum)

    @property
    def buffer(self):
        """Get the result buffer of the transformation.

        This imports seamless.workflow"""
        from seamless.workflow.core.direct.run import fingertip

        result_checksum = self.checksum
        if result_checksum.value is None:
            return None
        buf = fingertip(result_checksum.hex())
        if buf is None:
            raise CacheMissError(result_checksum)
        return buf

    async def get_buffer(self):
        """Get the result buffer of the transformation, asynchronously.

        This imports seamless.workflow"""
        from seamless.workflow.core.direct.run import fingertip_async

        result_checksum = self.checksum
        if result_checksum.value is None:
            return None
        buf = await fingertip_async(result_checksum.hex())
        if buf is None:
            raise CacheMissError(result_checksum)
        return buf

    @property
    def value(self):
        """Get the result of the transformation.

        This imports seamless.workflow"""
        if not self.checksum:
            return None
        buf = self.buffer
        if buf is None:
            return None
        return deserialize_sync(buf, self.checksum.bytes(), self.celltype, copy=True)

    async def get_value(self):
        """Get the result of the transformation, asynchronously.

        This imports seamless.workflow"""
        if not self.checksum:
            return None
        buf = await self.get_buffer()
        if buf is None:
            return None
        return await deserialize(buf, self.checksum.bytes(), self.celltype, copy=True)

    async def _run(self):
        from seamless.checksum.deserialize import deserialize

        await self.computation()
        buf = await self.get_buffer()
        return await deserialize(buf, self.checksum.bytes(), self.celltype, copy=True)

    def task(self) -> asyncio.Task:
        """Compute the transformation as an asynchronous task"""
        coro = self._run()
        return asyncio.get_event_loop().create_task(coro)

    @property
    def celltype(self):
        """The result celltype"""
        return self._result_celltype

    @property
    def exception(self):
        """The stored exception of the transformation"""
        return self._exception

    @property
    def logs(self):
        """Get the transformation logs.

        This imports seamless.workflow"""
        from seamless.workflow.core.cache.transformation_cache import (
            transformation_cache,
        )

        checksum = self.as_checksum()
        if not checksum:
            return None
        logs = transformation_cache.transformation_logs.get(checksum)
        if logs is not None:
            return logs

    def clear_exception(self):
        """Clear the stored exception.
        Typically, this allows re-running the transformation after it failed."""
        self._exception = None
        if self._resolved and not Checksum(self._transformation_checksum):
            self._resolved = False
        elif self._evaluated and not Checksum(self._result_checksum):
            self._evaluated = False

    @property
    def status(self):
        """The status of the transformation.

        The same as transformer status."""
        try:
            if self._exception is not None:
                return "Status: exception"
            if self._evaluated:
                assert Checksum(self._result_checksum)
                return "Status: OK"
            if self._future is not None:
                return "Status: pending"
            return "Status: ready"
        except Exception:
            return "Status: unknown exception"

    def cancel(self) -> None:
        """Hard-cancels the transformation.

        This will send a cancel signal that will kill the transformation if
        it is running.

        The transformation is killed with a HardCancelError exception.
        Clearing the exception using Transformer.clear_exception
        will restart the transformation.

        This affects both local and remote execution.

        This imports seamless.workflow
        """
        from seamless.workflow.core.cache.transformation_cache import (
            transformation_cache,
        )

        tf_checksum = self._transformation_checksum
        tf_checksum = Checksum(tf_checksum)

        if not tf_checksum:
            return

        transformation_cache.hard_cancel(tf_checksum=tf_checksum)

    @property
    def execution_metadata(self) -> dict:
        """Execution metadata"""
        from seamless.checksum.database_client import database

        checksum = self.as_checksum()
        if not checksum:
            return None
        return database.get_metadata(checksum)

    def undo(self) -> str | None:
        """Attempt to undo a finished transformation.

        This may be useful in the case of non-reproducible transformations.

        While the correct solution is to make them deterministic, this method
        will allow repeated execution under various conditions, in order to
        investigate the issue.

        The database is contacted in order to contest the result.
        If the database returns an error message, that is returned as string.

        This imports seamless.workflow
        """
        from seamless.workflow.core.cache.transformation_cache import (
            transformation_cache,
        )

        result_checksum = Checksum(self.checksum)
        if not result_checksum:
            raise RuntimeError("Not a completed transformation")
        self._evaluated = False
        self._result_checksum = None
        self._future = None
        result = transformation_cache.undo(self.as_checksum().bytes())
        if not isinstance(result, bytes):
            return result


def transformation_from_dict(
    transformation_dict, result_celltype, upstream_dependencies=None
) -> Transformation:
    """Build and run a Transformation from a transformation dict.

    This imports seamless.workflow"""
    from seamless.workflow.core.direct.run import (
        run_transformation_dict,
        run_transformation_dict_async,
        prepare_transformation_dict,
    )
    from seamless.checksum.calculate_checksum import calculate_checksum

    transformation_dict_original = transformation_dict
    transformation_dict = deepcopy(transformation_dict)
    for k, v in list(transformation_dict.items()):
        if isinstance(v, tuple) and len(v) == 3 and isinstance(v[2], Transformation):
            transformation_dict[k] = transformation_dict_original[k]
    # The transformation dict will be updated by prepare_transformation_dict in the resolver

    if "__meta__" not in transformation_dict:
        transformation_dict["__meta__"] = {}

    def resolver_sync(transformation_obj):  # pylint: disable=unused-argument
        from seamless.checksum.buffer_cache import buffer_cache
        from seamless.checksum import buffer_remote

        prepare_transformation_dict(transformation_dict)
        transformation_buffer = tf_get_buffer(transformation_dict)
        transformation = calculate_checksum(transformation_buffer)
        buffer_cache.cache_buffer(transformation, transformation_buffer)
        buffer_remote.write_buffer(transformation, transformation_buffer)
        return transformation

    async def resolver_async(transformation_obj):
        return resolver_sync(transformation_obj)

    def evaluator_sync(transformation_obj):
        scratch = transformation_obj.scratch
        result_checksum = run_transformation_dict(
            transformation_dict, fingertip=False, scratch=scratch
        )
        return result_checksum

    async def evaluator_async(transformation_obj):
        scratch = transformation_obj.scratch
        result_checksum = await run_transformation_dict_async(
            transformation_dict, fingertip=False, scratch=scratch
        )
        return result_checksum

    return Transformation(
        result_celltype,
        resolver_sync,
        resolver_async,
        evaluator_sync,
        evaluator_async,
        upstream_dependencies,
        meta=transformation_dict["__meta__"],
    )

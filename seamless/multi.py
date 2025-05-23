"""Utilities for parallel execution. Syntax similar to multiprocessing.pool"""

import asyncio
import seamless

from seamless import Checksum
from seamless import Buffer
import tqdm


class TransformationPool:
    """Execute a fixed number of transformations in parallel"""

    def __init__(self, nparallel: int):
        self.nparallel = nparallel

    def apply(self, func, nindices: int, *, callback=None):
        """Apply func to each index N between 0 and nindices.

        func must return a seamless Transformation.

        The transformations will be run in parallel,
        with nparallel instances running at the same time.

        The list of completed transformations is returned.

        It is possible to give a callback, which will be called
        as callback(N, transformation) whenever a transformation
        finishes.

        """
        from seamless.direct import Transformation

        if asyncio.get_event_loop().is_running():
            todo = list(range(nindices))
            results = [None] * nindices
            transformations = [None] * self.nparallel
            transformation_indices = [None] * self.nparallel
            order = []

            done = 0
            while done < nindices:
                for n, transformation in list(enumerate(transformations)):
                    if transformation is not None:
                        if transformation.status == "Status: pending":
                            continue
                        done += 1
                        order.remove(n)
                        results[transformation_indices[n]] = transformation
                        transformations[n] = None
                        if callback is not None:
                            callback(transformation_indices[n], transformation)

                    if len(todo):
                        new_index = todo.pop(0)
                        transformation = func(new_index)
                        if not isinstance(transformation, Transformation):
                            raise TypeError(
                                f"func({new_index}) returned a {type(transformation)} instead of a Seamless transformation"  # pylint: disable=line-too-long
                            )
                        transformations[n] = transformation
                        transformation_indices[n] = new_index
                        order.append(n)
                        transformation.start()

                if len(order):
                    if len(order) == self.nparallel or len(todo) == 0:
                        transformation = transformations[order[0]]
                        if transformation.status == "Status: pending":
                            transformation.compute()

            return results
        else:
            fut = asyncio.ensure_future(
                self.apply_async(func, nindices, callback=callback)
            )
            asyncio.get_event_loop().run_until_complete(fut)
            return fut.result()

    async def apply_async(self, func, nindices: int, *, callback=None):
        """Apply func to each index N between 0 and nindices.

        func must return a seamless Transformation.

        The transformations will be run in parallel,
        with nparallel instances running at the same time.

        The list of completed transformations is returned.

        It is possible to give a callback, which will be called
        as callback(N, transformation) whenever a transformation
        finishes.
        """

        from seamless.direct import Transformation

        transformations = []
        for n in range(nindices):
            transformation = func(n)
            if not isinstance(transformation, Transformation):
                raise TypeError(
                    f"func({n}) returned a {type(transformation)} instead of a Seamless transformation"  # pylint: disable=line-too-long
                )
            transformations.append(transformation)

        semaphore = asyncio.Semaphore(self.nparallel)

        async def runner(n, transformation):
            async with semaphore:
                await transformation.computation()
                if callback:
                    callback(n, transformation)

        runners = [
            runner(n, transformation)
            for n, transformation in enumerate(transformations)
        ]
        await asyncio.gather(
            *runners
        )  # do not set return_exceptions; transformations themselves should store it
        return transformations

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):  # pylint: disable=redefined-builtin
        pass


class ContextPool:
    """Compute a fixed number of Seamless contexts in parallel.
    Parameters:
    - ctx: template context that is to be cloned
    - nparallel: number of contexts to be run in parallel.
    """

    def __init__(
        self,
        ctx: "seamless.workflow.highlevel.Context",
        nparallel: int,
        *,
        show_progress=False,
    ):
        self._contexts = []
        self.nparallel = nparallel
        self.graph = ctx.get_graph()
        self.show_progress = show_progress

    def __enter__(self):
        from seamless.workflow import Context

        self._contexts[:] = []
        if self.nparallel == 0:
            return

        ctx = Context()
        ctx.set_graph(self.graph)
        ctx.compute(report=10)
        ctx.compute(report=10)
        self._contexts.append(ctx)

        if self.show_progress:
            range_ = tqdm.trange
        else:
            range_ = range
        for n in range(1, self.nparallel):
            ctx = Context()
            ctx._manager.CLEAR_NEW_TRANSFORMER_EXCEPTIONS = False
            ctx.set_graph(self.graph)
            self._contexts.append(ctx)

        for n in range_(self.nparallel):
            self._contexts[n].compute(report=None)
            self._contexts[n].compute(report=None)

        return self

    def __exit__(self, type, value, traceback):  # pylint: disable=redefined-builtin
        for ctx in self._contexts.copy():
            del ctx  # pylint: disable=modified-iterating-list
        self._contexts[:] = []

    def apply(self, setup_func, nindices: int, result_func):
        """Runs a separate Seamless context for each index N between 0 and nindices.

        The contexts will be run in parallel,
        with nparallel contexts running at the same time.

        Whenever a context ctx is free, invokes setup_func(ctx, N).
        Then, invoke ctx.computation()

        Finally, invokes result_func(ctx, N) to collect the results.

        This is repeated until every N has been processed
        """

        if asyncio.get_event_loop().is_running():
            raise NotImplementedError

        else:
            fut = asyncio.ensure_future(
                self.apply_async(setup_func, nindices, result_func)
            )
            asyncio.get_event_loop().run_until_complete(fut)
            return fut.result()

    async def apply_async(self, setup_func, nindices: int, result_func):
        """Runs a separate Seamless context for each index N between 0 and nindices.

        The contexts will be run in parallel,
        with nparallel contexts running at the same time.

        Whenever a context ctx is free, invokes setup_func(ctx, N).
        Then, invoke ctx.computation()

        Finally, invokes result_func(ctx, N) to collect the results.

        This is repeated until every N has been processed
        """
        from seamless.workflow import Context

        contexts = self._contexts

        async def runner(ctx: Context):
            await ctx.computation(report=None)
            await ctx.computation(report=None)

        tasks = []
        task_indices = []
        initial_counter = min(self.nparallel, nindices)
        for n in range(initial_counter):
            ctx: Context = contexts[n]
            setup_func(ctx, n)
            task_indices.append(n)
            assert len(tasks) == n
            tasks.append(asyncio.ensure_future(runner(ctx)))

        counter = len(tasks)
        nrunning = len(tasks)
        while nrunning:
            tasks2 = [task for task in tasks if task is not None]
            assert len(tasks2) == nrunning
            done, _ = await asyncio.wait(tasks2, return_when=asyncio.FIRST_COMPLETED)
            for task in list(done):
                for nn, task2 in enumerate(tasks):
                    if task2 is task:
                        done_task = nn
                        task_index = task_indices[done_task]
                        break
                else:
                    raise Exception  # shouldn't happen  # pylint: disable=broad-exception-raised

                ctx: Context = contexts[done_task]
                result_func(ctx, task_index)

                if counter < nindices:
                    setup_func(ctx, counter)
                    tasks[done_task] = asyncio.ensure_future(runner(ctx))
                    task_indices[done_task] = counter
                    counter += 1
                else:
                    nrunning -= 1
                    tasks[done_task] = None


async def _resolve_single(cachemanager, checksum: "Checksum", celltype):
    buffer = await cachemanager.fingertip(checksum.bytes())
    if celltype is None:
        return buffer
    if celltype == "silk":
        celltype = "mixed"
    elif celltype == "module":
        celltype = "plain"

    outer_celltype = celltype
    inner_celltype = None
    if celltype in ("deepcell", "deepfolder", "folder"):
        outer_celltype = "plain"
        if celltype == "deepcell":
            inner_celltype = "mixed"
        else:
            inner_celltype = "bytes"

    outer_value = await Buffer(buffer, checksum=checksum).deserialize_async(
        celltype=outer_celltype, copy=False
    )
    if inner_celltype is None:
        return outer_value
    deep_keys = list(outer_value.keys())
    inner_checksums = [Checksum(outer_value[k]) for k in deep_keys]
    inner_values = await resolve(inner_checksums, nparallel=5, celltype=inner_celltype)
    return {k: v for k, v in zip(deep_keys, inner_values)}


async def _resolve(cachemanager, checksums, celltype, nparallel, callback):

    semaphore = asyncio.Semaphore(nparallel)

    async def runner(n, checksum):
        async with semaphore:
            result = await _resolve_single(cachemanager, checksum, celltype)
            if callback:
                callback(n, result)
            return result

    runners = [runner(n, checksum) for n, checksum in enumerate(checksums)]

    return await asyncio.gather(*runners)


def resolve(
    checksums: list["Checksum"],
    nparallel: int,
    *,
    celltype: str | None = None,
    callback=None,
) -> list:
    """Resolve a fixed number of checksums in parallel.
    Parameters:
    - checksums: list of checksums
    - nparallel: number of checksums to be resolved in parallel
    - celltype (optional): the celltype to resolve to.

    It is possible to give a callback, which will be called
    as callback(N, value) whenever a resolve finishes.
    """
    from seamless.workflow.core.manager import Manager
    from seamless.checksum.celltypes import celltypes

    allowed_celltypes = celltypes + [
        "deepcell",
        "deepfolder",
        "folder",
        "module",
    ]
    if celltype not in allowed_celltypes:
        raise TypeError(celltype, allowed_celltypes)

    if asyncio.get_event_loop().is_running():
        raise RuntimeError(
            "seamless.multi.resolve does not work with a running event loop, e.g inside Jupyter"
        )

    manager = Manager()
    cachemanager = manager.cachemanager
    checksums = [Checksum(v) for v in checksums]
    nparallel = int(nparallel)
    if celltype in ["deepcell", "deepfolder", "folder"]:
        nparallel = int(nparallel / 5 + 0.9999)
    coro = _resolve(cachemanager, checksums, celltype, nparallel, callback)
    fut = asyncio.ensure_future(coro)
    asyncio.get_event_loop().run_until_complete(fut)
    return fut.result()

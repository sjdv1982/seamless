"""Utilities for parallel execution. Syntax similar to multiprocessing.pool"""

import asyncio
import time


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
        import asyncio
        from seamless.highlevel.direct.Transformation import Transformation
        
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
                                f"func({new_index}) returned a {type(transformation)} instead of a Seamless transformation"
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
            fut = asyncio.ensure_future(self.apply_async(func, nindices, callback=callback))
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

        from seamless.highlevel.direct.Transformation import Transformation

        transformations = []
        for n in range(nindices):
            transformation = func(n)
            if not isinstance(transformation, Transformation):
                raise TypeError(
                    f"func({n}) returned a {type(transformation)} instead of a Seamless transformation"
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

    def __exit__(self, type, value, traceback):
        pass


class ContextPool:
    """Compute a fixed number of Seamless contexts in parallel.
    Parameters:
    - ctx: template context that is to be cloned
    - nparallel: number of contexts to be run in parallel.
    """

    def __init__(self, ctx: "seamless.highlevel.Context", nparallel: int):
        self.nparallel = nparallel
        self.graph = ctx.get_graph()

    def __enter__(self):
        from seamless.highlevel import Context

        self._contexts = []
        if self.nparallel == 0:
            return
        
        ctx = Context()
        ctx.set_graph(self.graph)
        ctx.compute(report=10)
        ctx.compute(report=10)
        self._contexts.append(ctx)

        for n in range(1, self.nparallel):
            ctx = Context()
            ctx._manager.CLEAR_NEW_TRANSFORMER_EXCEPTIONS = False
            ctx.set_graph(self.graph)
            self._contexts.append(ctx)

        for n in range(self.nparallel):
            self._contexts[n].compute(report=None)
            self._contexts[n].compute(report=None)

        return self

    def __exit__(self, type, value, traceback):
        for ctx in self._contexts:
            del ctx

    def apply(self, setup_func, nindices: int, result_func):
        """Runs a separate Seamless context for each index N between 0 and nindices.

        The contexts will be run in parallel,
        with nparallel contexts running at the same time.

        Whenever a context ctx is free, invokes setup_func(ctx, N).
        Then, invoke ctx.computation()

        Finally, invokes result_func(ctx, N) to collect the results.

        This is repeated until every N has been processed
        """
        import asyncio

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

        contexts = self._contexts

        async def runner(ctx):
            await ctx.computation(report=None)
            await ctx.computation(report=None)

        tasks = []
        task_indices = []
        initial_counter = min(self.nparallel, nindices)
        for n in range(initial_counter):
            ctx = contexts[n]
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
                for nn in range(len(tasks)):
                    if tasks[nn] is task:
                        done_task = nn
                        task_index = task_indices[done_task]
                        break
                else:
                    raise Exception  # shouldn't happen

                ctx = contexts[done_task]
                result_func(ctx, task_index)

                if counter < nindices:
                    setup_func(ctx, counter)
                    tasks[done_task] = asyncio.ensure_future(runner(ctx))
                    task_indices[done_task] = counter
                    counter += 1
                else:
                    nrunning -= 1
                    tasks[done_task] = None

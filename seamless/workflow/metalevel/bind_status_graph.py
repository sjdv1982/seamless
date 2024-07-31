from functools import partial
import functools
import time
import weakref
import asyncio
from copy import deepcopy

OBSERVE_GRAPH_DELAY = 0.23 # 23 is not a multiple of 50
OBSERVE_STATUS_DELAY = 0.5
OBSERVE_STATUS_DELAY2 = 0.2

status_observers = []

class StatusObserver:
    def __init__(self, ctx, status_ctx):
        self.ctx = weakref.ref(ctx)
        self.status_ctx = weakref.ref(status_ctx)
        self.status = {}
        self._dirty = True
        self.observers = {}
        self.last_time = None
        self.runner = asyncio.ensure_future(self._run())

    def _callback(self, path, status):
        path2 = ".".join(path)
        if status is None:
            self.status.pop(path2, None)
        else:
            self.status[path2] = status
        self._dirty = True
        self._update()

    def _update(self):
        if not self._dirty:
            return
        t = time.time()
        if self.last_time is None or t - self.last_time > OBSERVE_STATUS_DELAY2:
            ctx, status_ctx = self.ctx(), self.status_ctx()
            if ctx is None or status_ctx is None:
                return
            if ctx._gen_context is None or status_ctx._gen_context is None:
                return
            if ctx._gen_context._destroyed or status_ctx._gen_context._destroyed:
                return
            try:
                c = status_ctx.status_
                if not isinstance(c, Cell):
                    return
                c.set(self.status)
            except Exception:
                pass
            self.last_time = t
            self._dirty = False

    async def _run(self):
        while 1:
            await asyncio.sleep(OBSERVE_STATUS_DELAY2)
            self._update()

    def observe(self, path):
        ctx, status_ctx = self.ctx(), self.status_ctx()
        if ctx is None or status_ctx is None:
            return
        callback = functools.partial(self._callback, path)
        callback(None)
        observer = ctx.observe(path, callback, OBSERVE_STATUS_DELAY, observe_none=True)
        self.destroy(path)
        self.observers[path] = observer



    def destroy(self, path):
        observer = self.observers.pop(path, None)
        if observer is None:
            return
        callback = observer.callback
        observer.destroy()
        callback(None)


def observe_graph(ctx, status_ctx, graph):
    try:
        graph_rt = status_ctx.graph_rt
    except AttributeError:
        graph_rt = None
    if isinstance(graph_rt, Cell):
        graph_rt.set(deepcopy(graph))
    else:
        try:
            graph_cell = status_ctx.graph
        except AttributeError:
            graph_cell = None
        if isinstance(graph_cell, Cell):
            graph_cell.set(deepcopy(graph))

    for status_observer in status_observers:
        if status_observer.ctx() is ctx and status_observer.status_ctx() is status_ctx:
            break
    else:
        status_observer = StatusObserver(ctx, status_ctx)
        status_observers.append(status_observer)

    paths_to_delete = set(status_observer.observers.keys())
    for node in graph["nodes"]:
        path = tuple(node["path"])
        if node["type"] == "cell":
            paths = [path]
        elif node["type"] == "transformer":
            paths = [
                path,
                path + (node["INPUT"],),
            ]
        else: # TODO: macro
            continue
        for path in paths:
            for attr in ("status", "exception"):
                subpath = path + (attr,)
                if subpath in status_observer.observers:
                    paths_to_delete.discard(subpath)
                status_observer.observe(subpath)
    for dpath in paths_to_delete:
        status_observer.destroy(dpath)
    #print("DONE")

def bind_status_context(ctx, status_ctx):
    """"Sets up monitoring of ctx by status visualization context status_ctx

The status context must have cells called "graph" and/or "graph_rt",
 (for ctx's static graph and the runtime graph, respectively),
 and a cell called "status_".
"""
    observe_graph_bound = partial(
        observe_graph, ctx, status_ctx
    )

    params = {"runtime": True}

    # Primary observation of realtime graph.
    # Send to status_ctx.graph_rt if it exists, else to status_ctx.graph.
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY, params=params)
    def observe2(graph):
        try:
            graphc = status_ctx.graph
        except AttributeError:
            graphc = None
        if not isinstance(graphc, Cell):
            return
        graphc.set(deepcopy(graph))
    
    # Secondary observation of static graph.
    # Only if both status_ctx.graph and status_ctx.graph_rt exist
    try:
        graph_rt = status_ctx.graph_rt
        if not isinstance(graph_rt, Cell):
            raise AttributeError
        graph = status_ctx.graph
        if not isinstance(graph, Cell):
            raise AttributeError
    except AttributeError:
        pass
    else:
        ctx.observe(("get_graph",), observe2, OBSERVE_GRAPH_DELAY)
    
def bind_status_graph(ctx, status_graph, *, zips=None, mounts=False, shares=True):
    """"Creates status visualization context that will monitor the status of ctx

The status visualization context is loaded from status_graph, 
 which must be a workflow in JSON format, from a .seamless file.
The status context's underlying buffers must be available already
(from add_zip or via Seamless database) or provided with "zips"
The status context must have cells called "graph" and/or "graph_rt",
 (for ctx's static graph and the runtime graph, respectively),
 a cell called "status_", and normally, also a cell shared as "index.html".
The status context will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.workflow import Context
    status_ctx = Context()
    if zips is not None:
        for zipf in zips:
            status_ctx.add_zip(zipf)
    status_ctx.share_namespace="status"
    status_ctx.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    status_ctx.translate()

    bind_status_context(ctx, status_ctx)
    return status_ctx

async def bind_status_graph_async(ctx, status_graph, *, zips=None, mounts=False, shares=True):
    """"Creates status visualization context that will monitor the status of ctx

The status visualization context is loaded from status_graph, 
 which must be a workflow in JSON format, from a .seamless file.
The status context's underlying buffers must be available already
(from add_zip or via Seamless database) or provided with "zips"
The status context must have cells called "graph" and/or "graph_rt",
 (for ctx's static graph and the runtime graph, respectively),
 a cell called "status_", and normally, also a cell shared as "index.html".
The status context will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.workflow import Context
    status_ctx = Context()
    if zips is not None:
        for zipf in zips:
            status_ctx.add_zip(zipf)
    status_ctx.share_namespace="status"
    status_ctx.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    await status_ctx.translation()
    bind_status_context(ctx, status_ctx)
    return status_ctx

from seamless.workflow import Cell
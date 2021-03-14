from functools import partial
import functools
import time
import weakref
import asyncio

OBSERVE_GRAPH_DELAY = 0.23 # 23 is not a multiple of 50
OBSERVE_STATUS_DELAY = 0.5
OBSERVE_STATUS_DELAY2 = 0.2

status_observers = []

class StatusObserver:
    def __init__(self, ctx, ctx2):
        self.ctx = weakref.ref(ctx)
        self.ctx2 = weakref.ref(ctx2)
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
            ctx, ctx2 = self.ctx(), self.ctx2()
            if ctx is None or ctx2 is None:
                return
            if ctx._gen_context is None or ctx2._gen_context is None:
                return
            if ctx._gen_context._destroyed or ctx2._gen_context._destroyed:
                return
            try:
                c = ctx2.status_
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
        ctx, ctx2 = self.ctx(), self.ctx2()
        if ctx is None or ctx2 is None:
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


def observe_graph(ctx, ctx2, graph):
    from copy import deepcopy
    ctx2.graph.set(deepcopy(graph))
    for status_observer in status_observers:
        if status_observer.ctx() is ctx and status_observer.ctx2() is ctx2:
            break
    else:
        status_observer = StatusObserver(ctx, ctx2)
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

def bind_status_graph(ctx, status_graph, *, zips=None, mounts=False, shares=True):
    """"Creates context that will monitor the status of ctx

The context is loaded from status_graph, which must be a graph in JSON format.
It uses the same manager as ctx.
The status graph's underlying buffers must be available already
(from add_zip or via Seamless database)
The status graph must have a cell called "graph",
 and normally, also a cell shared as "index.html"
The status graph will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.highlevel import Context
    ctx2 = Context()
    if zips is not None:
        for zipf in zips:
            ctx2.add_zip(zipf)
    ctx2.share_namespace="status"
    ctx2.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    assert "graph" in ctx2.children()
    observe_graph_bound = partial(
        observe_graph, ctx, ctx2
    )
    ctx2.translate()
    params = {"runtime": True}
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY, params=params)
    return ctx2

async def bind_status_graph_async(ctx, status_graph, *, zips=None, mounts=False, shares=True):
    """"Creates context that will monitor the status of ctx

The context is loaded from status_graph, which must be a graph in JSON format.
It uses the same manager as ctx.
The status graph's underlying buffers must be available already
(from add_zip or via database)
The status graph must have a cell called "graph",
 and normally, also a cell shared as "index.html"
The status graph will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.highlevel import Context
    ctx2 = Context()
    if zips is not None:
        for zipf in zips:
            ctx2.add_zip(zipf)
    ctx2.share_namespace="status"
    ctx2.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    assert "graph" in ctx2.children()
    observe_graph_bound = partial(
        observe_graph, ctx, ctx2,
    )
    await ctx2.translation()
    params = {"runtime": True}
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY, params=params)
    return ctx2

from seamless.highlevel import Cell
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
    def __init__(self, ctx, webctx):
        self.ctx = weakref.ref(ctx)
        self.webctx = weakref.ref(webctx)
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
            ctx, webctx = self.ctx(), self.webctx()
            if ctx is None or webctx is None:
                return
            if ctx._gen_context is None or webctx._gen_context is None:
                return
            if ctx._gen_context._destroyed or webctx._gen_context._destroyed:
                return
            try:
                c = webctx.status_
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
        ctx, webctx = self.ctx(), self.webctx()
        if ctx is None or webctx is None:
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


def observe_graph(ctx, webctx, graph):
    try:
        graph_rt = webctx.graph_rt
    except AttributeError:
        graph_rt = None
    if isinstance(graph_rt, Cell):
        graph_rt.set(deepcopy(graph))
    else:
        try:
            graph_cell = webctx.graph
        except AttributeError:
            graph_cell = None
        if isinstance(graph_cell, Cell):
            graph_cell.set(deepcopy(graph))

    for status_observer in status_observers:
        if status_observer.ctx() is ctx and status_observer.webctx() is webctx:
            break
    else:
        status_observer = StatusObserver(ctx, webctx)
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
    """"Creates status visualization context that will monitor the status of ctx

The status visualization context is loaded from status_graph, 
 which must be a workflow in JSON format, from a .seamless file.
It uses the same manager as ctx.
The status context's underlying buffers must be available already
(from add_zip or via Seamless database) or provided with "zips"
The status context must have cells called "graph" and "graph_rt",
 (for ctx's static graph and the runtime graph, respectively)
 and normally, also a cell shared as "index.html".
The status context will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.highlevel import Context
    webctx = Context()
    if zips is not None:
        for zipf in zips:
            webctx.add_zip(zipf)
    webctx.share_namespace="status"
    webctx.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    assert "graph" in webctx.get_children()
    observe_graph_bound = partial(
        observe_graph, ctx, webctx
    )
    webctx.translate()
    params = {"runtime": True}
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY, params=params)
    def observe2(graph):
        try:
            graph_rt = webctx.graph_rt
        except AttributeError:
            graph_rt = None
        if not isinstance(graph_rt, Cell):
            return
        webctx.graph.set(deepcopy(graph))
    ctx.observe(("get_graph",), observe2, OBSERVE_GRAPH_DELAY)
    return webctx

async def bind_status_graph_async(ctx, status_graph, *, zips=None, mounts=False, shares=True):
    """"Creates status visualization context that will monitor the status of ctx

The status visualization context is loaded from status_graph, 
 which must be a workflow in JSON format, from a .seamless file.
It uses the same manager as ctx.
The status context's underlying buffers must be available already
(from add_zip or via Seamless database) or provided with "zips"
The status context must have cells called "graph" and "graph_rt",
 (for ctx's static graph and the runtime graph, respectively)
 and normally, also a cell shared as "index.html".
The status context will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph

Additional zips can be provided.
They will be passed to ctx.add_zip before the graph is loaded
"""
    from seamless.highlevel import Context
    webctx = Context()
    if zips is not None:
        for zipf in zips:
            webctx.add_zip(zipf)
    webctx.share_namespace="status"
    webctx.set_graph(
        status_graph,
        mounts=mounts,
        shares=shares
    )
    assert "graph" in webctx.get_children()
    observe_graph_bound = partial(
        observe_graph, ctx, webctx,
    )
    await webctx.translation()
    params = {"runtime": True}
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY, params=params)
    def observe2(graph):
        try:
            graph_rt = webctx.graph_rt
        except AttributeError:
            graph_rt = None
        if not isinstance(graph_rt, Cell):
            return
        webctx.graph.set(deepcopy(graph))
    ctx.observe(("get_graph",), observe2, OBSERVE_GRAPH_DELAY)
    return webctx

from seamless.highlevel import Cell
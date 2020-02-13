from functools import partial

status_callbacks = {}

OBSERVE_GRAPH_DELAY = 0.5
OBSERVE_STATUS_DELAY = 2

def status_callback(ctx, ctx2, path, status):
    if ctx._gen_context is None or ctx2._gen_context is None:
        return
    if ctx._gen_context._destroyed or ctx2._gen_context._destroyed:
        return
    handle = ctx2.status_.handle
    path2 = ".".join(path)
    handle[path2] = status

def observe_graph(ctx, ctx2, graph):
    ctx2.graph.set(graph)    
    paths_to_delete = set(status_callbacks.keys())
    for node in graph["nodes"]:
        path = tuple(node["path"])
        if node["type"] == "cell":
            paths = [path]
        elif node["type"] == "transformer":
            paths = [
                path,
                path + (node["INPUT"],),
            ]
        else: # TODO: libmacro, macro, reactor
            continue        
        for path in paths:            
            if path in status_callbacks:
                paths_to_delete.discard(path)
                continue
            #print("OBSERVE", path)
            observers = {}
            for attr in ("status", "exception"):
                subpath = path + (attr,)
                callback = partial(status_callback, ctx, ctx2, subpath)
                status_callback(ctx, ctx2, subpath, None)
                observer = ctx.observe(subpath, callback, OBSERVE_STATUS_DELAY, observe_none=True)
                observers[subpath] = observer
            status_callbacks[path] = observers
    for dpath in paths_to_delete:
        #print("DELETE", dpath)
        observers = status_callbacks.pop(dpath)
        for subpath, observer in observers.items():
            status_callback(ctx, ctx2, subpath, None)
            observer.destroy()
    #print("DONE")

def bind_status_graph(ctx, status_graph, *, mounts=False, shares=True):
    """"Creates context that will monitor the status of ctx

The context is loaded from status_graph, which must be a graph in JSON format.
It uses the same manager as ctx.
The status graph's underlying buffers must be available already 
(from add_zip or via Redis)
The status graph must have a cell called "graph", 
 and normally, also a cell shared as "index.html"
The status graph will receive the share namespace "status"

mounts and shares have the same meaning as in from_graph
"""
    from seamless.highlevel import Context
    ctx2 = Context.from_graph(
        status_graph, 
        manager=ctx._manager,
        mounts=mounts,
        shares=shares
    )
    ctx2.share_namespace = "status"
    assert "graph" in ctx2.children()
    observe_graph_bound = partial(
        observe_graph, ctx, ctx2
    )
    ctx.observe(("get_graph",), observe_graph_bound, OBSERVE_GRAPH_DELAY)
    return ctx2
# https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js
import os; os.system("pip install mrcfile --no-dependencies")

from seamless.highlevel import Context, Transformer, Cell, load_graph
from functools import partial

def save(): 
    ctx.save_graph("graph.seamless") 
    ctx.save_zip("graph.zip") 

ctx = load_graph("graph.seamless", mounts=True, shares=True)
ctx.add_zip("graph.zip")
ctx.translate(force=True) # kludge

print("Open http://localhost:5813/ctx/index.html in the browser")


def vis():
    global ctx2
    ctx2 = load_graph("state-visualization-graph.seamless", shares=True, mounts=False)
    ctx2.add_zip("state-visualization-graph.zip")

    state_callbacks = {}

    def state_callback(path, state):
        if ctx._gen_context is None or ctx2._gen_context is None:
            return
        if ctx._gen_context._destroyed or ctx2._gen_context._destroyed:
            return
        handle = ctx2.state.handle
        path2 = ".".join(path)
        handle[path2] = state

    def observe_graph(graph):
        ctx2.graph.set(graph)    
        paths_to_delete = set(state_callbacks.keys())
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
                if path in state_callbacks:
                    paths_to_delete.discard(path)
                    continue
                #print("OBSERVE", path)
                observers = {}
                for attr in ("status", "exception"):
                    subpath = path + (attr,)
                    callback = partial(state_callback, subpath)
                    state_callback(subpath, None)
                    observer = ctx.observe(subpath, callback, 2, observe_none=True)
                    observers[subpath] = observer
                state_callbacks[path] = observers
        for dpath in paths_to_delete:
            #print("DELETE", dpath)
            observers = state_callbacks.pop(dpath)
            for subpath, observer in observers.items():
                state_callback(subpath, None)
                observer.destroy()
        #print("DONE")

    ctx.observe(("get_graph",), observe_graph, 0.5)

    ctx2.translate()
    print("Open http://localhost:5813/ctx1/state-visualization.html in the browser")

print("")
print("*" * 80)
print("type 'vis()' to start graph visualization, 'save()' to save, don't forget ctx.translate()")
print("*" * 80)
print()
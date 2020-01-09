from seamless.highlevel import Context, Transformer, Cell
from functools import partial

ctx = Context()
ctx.auto_translate = True
ctx.a = 42
ctx.b = ctx.a

ctx2 = Context()
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.state = {}
ctx2.state_data = ctx2.state
ctx2.state_data.celltype = "plain"
ctx2.state_data.mount("/tmp/state.json", "w")
ctx2.translate()

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

gvs = ctx2.gen_vis_state = Transformer()
gvs.graph = ctx2.graph
gvs.state = ctx2.state
gvs.code.mount("gen_vis_state.py", authority="file")
ctx2.vis_state = ctx2.gen_vis_state
ctx2.vis_state.celltype = "plain"
ctx2.vis_state.share(readonly=True)

c = ctx2.html = Cell()
c.set(open("state-visualization.html").read())
c.celltype = "text"
c.mimetype = "text/html"
c.share(path="state-visualization.html")

import seamless, os
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx2.js = Cell()
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.celltype = "text"
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx2.js2 = Cell()
c.set(open("state-visualization.js").read())
c.celltype = "text"
c.mimetype = "text/javascript"
c.share(path="state-visualization.js")

c = ctx2.css = Cell()
c.set(open("state-visualization.css").read())
c.celltype = "text"
c.mimetype = "text/css"
c.share(path="state-visualization.css")

ctx2.translate()
print("Open http://localhost:5813/ctx/state-visualization.html in the browser")
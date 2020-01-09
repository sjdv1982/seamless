import seamless
from seamless.highlevel import Context, Transformer, Cell
from seamless.silk.Silk import RichValue
import json
import numpy as np
from functools import partial

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)
ctx.add_zip("snakegraph.zip")
ctx.translate()

print("Load state visualization context (adapted from visualize-graph test)")
ctx2 = Context()
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.state = {}
ctx2.state_data = ctx2.state
ctx2.state_data.celltype = "plain"
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
            observers = {}
            for attr in ("status", "exception"):
                subpath = path + (attr,)
                callback = partial(state_callback, subpath)
                state_callback(subpath, None)
                observer = ctx.observe(subpath, callback, 2, observe_none=True)
                observers[subpath] = observer
            state_callbacks[path] = observers
    for dpath in paths_to_delete:
        observers = state_callbacks.pop(dpath)
        for subpath, observer in observers.items():
            state_callback(subpath, None)
            observer.destroy()

ctx.observe(("get_graph",), observe_graph, 0.5)

gvs = ctx2.gen_vis_state = Transformer()
gvs.graph = ctx2.graph
gvs.state = ctx2.state
gvs.code = open("gen_vis_state.py").read()
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

print("Setup binding of files")

def bind(file, mode):
    data = open(file, "r" + mode).read()
    if mode == "b":
        data = np.frombuffer(data, dtype=np.uint8)
    setattr(ctx.fs, file, data)

def list_files():
    print("File system contents:")
    for fs_cellname in ctx.fs.children("cell"):
        fs_cell = getattr(ctx.fs, fs_cellname)
        value = fs_cell.value
        value2 = RichValue(value, need_form=True)
        if value2.value is None:
            continue
        if value2.storage == "pure-plain":
            v = str(value2.value)
            if len(v) > 80:
                v = v[:35] + "." * 10  + v[-35:]
        else:
            v = "< Binary data, length %d >" % len(value)
        print(fs_cellname + ":", v)
        print()


ctx2.translate()
ctx2.compute()
print("""
*********************************************************************
*  Interactive setup complete.
*********************************************************************

- Open http://localhost:5813/ctx/state-visualization.html in the browser")
- Periodically enter the command "list_files()" to list the current files
- Enter the following commands:
  
  bind("data/genome.tgz", "b")
  bind("data/samples/A.fastq", "t")
  bind("data/samples/B.fastq", "t")

- "ctx.compute()" or "await ctx.computation()" 
   will block until the workflow is complete
""")
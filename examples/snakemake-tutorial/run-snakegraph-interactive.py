import seamless
from seamless.highlevel import Context, Transformer, Cell
from silk.Silk import RichValue
import json, os
import numpy as np
from functools import partial

print("Load graph...")
graph = json.load(open("snakegraph.seamless"))
ctx = seamless.highlevel.load_graph(graph)
ctx.add_zip("snakegraph.zip")
ctx.translate()

print("Load status visualization context (adapted from visualize-graph test)")
ctx2 = Context()
ctx2.share_namespace = "status"
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.status_ = {}
ctx2.status_data = ctx2.status_
ctx2.status_data.celltype = "plain"
ctx2.translate()

status_callbacks = {}

def status_callback(path, status):
    if ctx._gen_context is None or ctx2._gen_context is None:
        return
    if ctx._gen_context._destroyed or ctx2._gen_context._destroyed:
        return
    handle = ctx2.status_.handle
    path2 = ".".join(path)
    handle[path2] = status

def observe_graph(graph):
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
        else: # TODO: libinstance, macro, reactor
            continue
        for path in paths:
            if path in status_callbacks:
                paths_to_delete.discard(path)
                continue
            observers = {}
            for attr in ("status", "exception"):
                subpath = path + (attr,)
                callback = partial(status_callback, subpath)
                status_callback(subpath, None)
                observer = ctx.observe(subpath, callback, 2, observe_none=True)
                observers[subpath] = observer
            status_callbacks[path] = observers
    for dpath in paths_to_delete:
        observers = status_callbacks.pop(dpath)
        for subpath, observer in observers.items():
            status_callback(subpath, None)
            observer.destroy()

ctx.observe(("get_graph",), observe_graph, 0.5)

seamless_dir = os.path.dirname(seamless.__file__)
graph_dir = seamless_dir + "/graphs/status-visualization/"

gvs = ctx2.gen_vis_status = Transformer()
gvs.graph = ctx2.graph
gvs.status_ = ctx2.status_
gvs.code = open(graph_dir + "gen_vis_status.py").read()
ctx2.vis_status = ctx2.gen_vis_status
ctx2.vis_status.celltype = "plain"
ctx2.vis_status.share(readonly=True)

c = ctx2.html = Cell()
c.set(open(graph_dir + "status-visualization.html").read())
c.celltype = "text"
c.mimetype = "text/html"
c.share(path="status-visualization.html")

c = ctx2.js = Cell()
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.celltype = "text"
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx2.js2 = Cell()
c.set(open(graph_dir + "status-visualization.js").read())
c.celltype = "text"
c.mimetype = "text/javascript"
c.share(path="status-visualization.js")

c = ctx2.css = Cell()
c.set(open(graph_dir + "status-visualization.css").read())
c.celltype = "text"
c.mimetype = "text/css"
c.share(path="status-visualization.css")

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

- Open http://localhost:5813/status/status-visualization.html in the browser")
- Periodically enter the command "list_files()" to list the current files
- Enter the following commands:

  bind("data/genome.tgz", "b")
  bind("data/samples/A.fastq", "t")
  bind("data/samples/B.fastq", "t")

- "ctx.compute()" or "await ctx.computation()"
   will block until the workflow is complete
""")
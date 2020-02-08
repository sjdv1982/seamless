from seamless.highlevel import Context, Transformer, Cell
from functools import partial

ctx = Context()
ctx.auto_translate = True
ctx.a = 42
ctx.b = ctx.a

ctx2 = Context()
ctx2.share_namespace = "status"
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.status_ = {}
ctx2.status_data = ctx2.status_
ctx2.status_data.celltype = "plain"
###ctx2.status_data.mount("/tmp/status.json", "w")
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
                callback = partial(status_callback, subpath)
                status_callback(subpath, None)
                observer = ctx.observe(subpath, callback, 2, observe_none=True)
                observers[subpath] = observer
            status_callbacks[path] = observers
    for dpath in paths_to_delete:
        #print("DELETE", dpath)
        observers = status_callbacks.pop(dpath)
        for subpath, observer in observers.items():
            status_callback(subpath, None)
            observer.destroy()
    #print("DONE")

ctx.observe(("get_graph",), observe_graph, 0.5)

gvs = ctx2.gen_vis_status = Transformer()
gvs.graph = ctx2.graph
gvs.status_ = ctx2.status_
gvs.code.mount("gen_vis_status.py", authority="file")
ctx2.vis_status = ctx2.gen_vis_status
ctx2.vis_status.celltype = "plain"
ctx2.vis_status.share(readonly=True)

c = ctx2.html = Cell()
c.set(open("status-visualization.html").read())
c.celltype = "text"
c.mimetype = "text/html"
c.share(path="index.html")

import seamless, os
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx2.js = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx2.css = Cell()
c.celltype = "text"
c.set(open("status-visualization.css").read())
c.mimetype = "text/css"
c.share(path="status-visualization.css")

ctx2.translate()
from seamless import shareserver
if shareserver.started:
    update_port = shareserver.update_port
    rest_port = shareserver.rest_port
    share_namespace = ctx2.live_share_namespace 

    c = ctx2.js2 = Cell()
    c.celltype = "text"
    status_vis = open("status-visualization.js").read()
    m1, m2 = "// START of config block", "// END of config block" 
    marker1 = status_vis.find(m1)
    marker2 = status_vis.find(m2)
    if marker1 > -1 and marker2 > marker1:
        config_block = """
    SEAMLESS_UPDATE_PORT={}
    SEAMLESS_REST_PORT={}
    SEAMLESS_SHARE_NAMESPACE="{}"
        """.format(update_port, rest_port, share_namespace)    
        status_vis = status_vis[:marker1] + config_block + status_vis[marker2+len(m2):]
    c.set(status_vis)
    c.mimetype = "text/javascript"
    c.share(path="status-visualization.js")

    ctx2.translate()

    msg = "Open http://localhost:{}/{} in the browser"
    print(msg.format(rest_port, share_namespace))
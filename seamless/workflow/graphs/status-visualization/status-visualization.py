"""Web status visualization graph
Visualizes the status of another Seamless context ctx in a web page
Use this status graph together with bind_status_graph,
 as `webctx = bind_status_graph(ctx, status_graph)`

Input cells are filled by bind_status_graph.
- webctx.graph with the static workflow graph of ctx 
  (stored in a .seamless file)
- webctx.graph_rt with the real-time workflow graph of ctx 
  (Unwrapping LibInstances, and including core.HighLevelContext instances)  
"""
from seamless.workflow import Context, Transformer, Cell

webctx = Context()
webctx.help = __doc__
webctx.share_namespace = "status"
webctx.graph = {}
webctx.graph.celltype = "plain"
webctx.graph.share()
webctx.graph_rt = {}
webctx.graph_rt.celltype = "plain"
webctx.graph_rt.share()
webctx.status_ = {}
webctx.status_data = webctx.status_
webctx.status_data.celltype = "plain"

gvs = webctx.get_visual_status = Transformer()
gvs.help = """Visual status generator.
Integrates the workflow graph and the status graph 
 into a single directed graph JSON structure with concrete colors that reflect the status.
This JSON graph can be directly visualized in the browser using status-visualization.js
"""
gvs.graph = webctx.graph_rt
gvs.status_ = webctx.status_
gvs.code.mount("get_visual_status.py", authority="file")
webctx.visual_status = webctx.get_visual_status
webctx.visual_status.celltype = "plain"
webctx.visual_status.share(readonly=True)

c = webctx["status-visualization.html"] = Cell()
c.set(open("status-visualization.html").read())
c.celltype = "text"
c.mimetype = "text/html"
c.share(path="index.html")

import seamless, os
seamless_dir = os.path.dirname(seamless.__file__)
c = webctx["seamless-client.js"] = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share("seamless-client.js")

c = webctx["status-visualization.js"] = Cell()
c.help = """Visualizer of a colored graph of Seamless statuses
Adapted from Directed Graph Editor (Copyright (c) 2013 Ross Kirsling)
  https://gist.github.com/rkirsling/5001347
"""
c.celltype = "text"
c.set(open("status-visualization.js").read())
c.mimetype = "text/javascript"
c.share(path="status-visualization.js")

c = webctx["status-visualization.css"] = Cell()
c.celltype = "text"
c.set(open("status-visualization.css").read())
c.mimetype = "text/css"
c.share(path="status-visualization.css")

webctx.compute()
webctx.save_graph("../status-visualization.seamless")
webctx.save_zip("../status-visualization.zip")
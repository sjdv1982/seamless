from seamless.highlevel import Context, Transformer, Cell
from functools import partial

ctx2 = Context()
ctx2.share_namespace = "status"
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.graph.share()
ctx2.graph_rt = {}
ctx2.graph_rt.celltype = "plain"
ctx2.status_ = {}
ctx2.status_data = ctx2.status_
ctx2.status_data.celltype = "plain"

gvs = ctx2.gen_vis_status = Transformer()
gvs.graph = ctx2.graph_rt
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
c = ctx2.seamless_client_js = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx2.status_visualization_js = Cell()
c.celltype = "text"
c.set(open("status-visualization.js").read())
c.mimetype = "text/javascript"
c.share(path="status-visualization.js")

c = ctx2.css = Cell()
c.celltype = "text"
c.set(open("status-visualization.css").read())
c.mimetype = "text/css"
c.share(path="status-visualization.css")

ctx2.compute()
ctx2.save_graph("../status-visualization.seamless")
ctx2.save_zip("../status-visualization.zip")
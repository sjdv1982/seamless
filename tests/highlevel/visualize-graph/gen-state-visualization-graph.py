from seamless.highlevel import Context, Transformer, Cell
from functools import partial

ctx2 = Context()
ctx2.graph = {}
ctx2.graph.celltype = "plain"
ctx2.state = {}
ctx2.state_data = ctx2.state
ctx2.state_data.celltype = "plain"

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
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share(path="seamless-client.js")

c = ctx2.js2 = Cell()
c.celltype = "text"
code = open("state-visualization.js").read()
code = code.replace('"ctx"','"ctx1"')
c.set(code)
c.mimetype = "text/javascript"
c.share(path="state-visualization.js")

c = ctx2.css = Cell()
c.celltype = "text"
c.set(open("state-visualization.css").read())
c.mimetype = "text/css"
c.share(path="state-visualization.css")

ctx2.compute()
ctx2.save_graph("state-visualization-graph.seamless")
ctx2.save_zip("state-visualization-graph.zip")
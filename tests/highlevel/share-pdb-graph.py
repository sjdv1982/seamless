import seamless
from seamless.highlevel import load_graph, Cell
import sys, json

graph = json.load(open("share-pdb.seamless"))

ctx = load_graph(graph)
ctx.add_zip("share-pdb.zip")
ctx.compute()

"""
# superfluous
ctx.bb_pdb.share()
ctx.pdb.share()
ctx.code.share(readonly=False)
ctx.translate()

ctx.code.mount("/tmp/code.bash")
ctx.translate()
"""

import seamless
import os
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx.seamless_client_js = Cell()
c.celltype = "text"
c.mount(seamless_dir + "/js/seamless-client.js", "r", authority="file-strict")
c.mimetype = "js"
c.share("seamless-client.js")
ctx.translate()
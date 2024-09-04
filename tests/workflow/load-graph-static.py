import seamless

seamless.delegate(False)

import json
from seamless import load_graph

graph = json.load(open("twopi-result.seamless"))
zipfile = "twopi-result.zip"

sctx = load_graph(graph, static=True)
sctx.add_zip(zipfile)
print(sctx.pi.value)
print(sctx.twopi.value)

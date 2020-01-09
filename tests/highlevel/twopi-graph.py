from math import pi
from seamless.core import context, cell
ctx0 = context(toplevel=True)
ctx0.cell = cell("mixed").set(pi)
ctx0.cell2 = cell("python").set("lambda a: 2 * a")
ctx0.cell.set({"a": pi})

import json
graph = json.load(open("twopi.seamless"))
from seamless.highlevel import load_graph
ctx = load_graph(graph, cache_ctx=ctx0)
ctx.translate(force=True)
print(ctx.pi.checksum)
print(ctx.pi.value)
print("compute")
ctx.compute()
print(ctx.twopi.value)

graph2 = json.load(open("twopi-result.seamless"))
ctx2 = load_graph(graph2, cache_ctx=ctx0)
print(ctx2.pi.checksum)
print(ctx2.pi.value)
print("compute")
ctx2.compute()
print(ctx2.twopi.value)
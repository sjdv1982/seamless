import json
import seamless
from seamless.highlevel import load_graph, Context

graph = json.load(open("twopi-result.seamless"))

ctx = Context()
ctx.load_vault("/tmp/seamless-vault")
ctx.set_graph(graph)
ctx.translate()
ctx.compute()

print(ctx.pi.checksum)
print(ctx.pi.value)
print(ctx.twopi.value)
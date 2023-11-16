import seamless
raise NotImplementedError
seamless.database_cache.connect()

import json
graph = json.load(open("twopi.seamless"))
from seamless.highlevel import load_graph
ctx = load_graph(graph)
ctx.translate(force=True)
print(ctx.pi.checksum)
print(ctx.pi.value)
print("compute")
ctx.compute()
print(ctx.twopi.value)

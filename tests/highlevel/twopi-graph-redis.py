import seamless
redis_cache = seamless.RedisCache()

import json
graph = json.load(open("twopi.seamless"))
from seamless.highlevel import load_graph
ctx = load_graph(graph)
ctx.translate(force=True)
print(ctx.pi.checksum)
print(ctx.pi.value)
print("equilibrate")
ctx.equilibrate()
print(ctx.twopi.value)

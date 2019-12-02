import json
import seamless
from seamless.highlevel import load_graph

redis_cache = seamless.RedisCache()

graph = json.load(open("twopi-result.seamless"))
sctx = load_graph(graph, static=True)
print(sctx.pi.value.value)
print(sctx.twopi.value.value)
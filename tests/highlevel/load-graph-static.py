import json
import seamless
from seamless.highlevel import load_graph

#redis_cache = seamless.RedisCache() # Only needed without zip

graph = json.load(open("twopi-result.seamless"))
zipfile = "twopi-result.zip"

sctx = load_graph(graph, static=True)
sctx.add_zip(zipfile)
print(sctx.pi.value.value)
print(sctx.twopi.value.value)

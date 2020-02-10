# TODO: proper command line options (also for mounts)
import seamless
import sys, json
from seamless.highlevel import load_graph
graph_file = sys.argv[1]
graph = json.load(open(graph_file))
ctx = load_graph(graph, mounts=False, shares=True)
if len(sys.argv) > 2:
    zipfile = sys.argv[2]
    ctx.add_zip(zipfile)
else:
    redis_sink = seamless.RedisSink()
    redis_cache = seamless.RedisCache()
ctx.translate()

import asyncio
asyncio.get_event_loop().run_forever()
import math
from seamless.highlevel import Context, Cell
import json

import seamless
redis_sink = seamless.RedisSink()

ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

graph = ctx.get_graph()
json.dump(graph, open("/tmp/twopi-redis.seamless", "w"), indent=2, sort_keys=True)
import os
os.system("md5sum twopi.seamless /tmp/twopi-redis.seamless")

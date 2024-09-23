import math
from seamless.workflow import Context, Cell
import json

import seamless

raise NotImplementedError
seamless.database_sink.connect()

ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

graph = ctx.get_graph()
json.dump(graph, open("/tmp/twopi-database.seamless", "w"), indent=2, sort_keys=True)
import os

os.system("md5sum twopi.seamless /tmp/twopi-database.seamless")

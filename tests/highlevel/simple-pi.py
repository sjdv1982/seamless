import math
from seamless.highlevel import Context, Cell
import json
ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
###ctx.doubleit.hash_pattern = {"*": "#"}
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

graph = ctx.get_graph()
print(json.dumps( graph, indent=2, sort_keys=True))
json.dump(graph, open("twopi.seamless", "w"), indent=2, sort_keys=True)

ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.doubleit.code = lambda a: 42
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.translate(force=True)
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)
print()

ctx.doubleit.code = lambda a: 2 * a
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

graph = ctx.get_graph()
json.dump(graph, open("twopi-result.seamless", "w"), indent=2, sort_keys=True)
archive = ctx.get_zip()
with open("twopi-result.zip", "wb") as f:
    f.write(archive) 
import os
os.system("md5sum twopi.seamless twopi-result.seamless twopi-result.zip")
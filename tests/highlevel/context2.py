from seamless.highlevel import Context

ctx = Context()
ctx.mount("/tmp/mount-test")

ctx.a = 12

def triple_it(a, b):
    print("3 * a + b, a = %s, b = %s" % (a, b))
    return 3 * a + b

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.transform.b = 6
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)

ctx2 = Context()
ctx2.sub = ctx
ctx2.sub2 = ctx
print(ctx2.sub.myresult.value)
ctx2.equilibrate()
print(ctx2.sub.myresult.value)

ctx2.sub.a = 3
ctx2.sub2.a = 5
ctx2.equilibrate()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)

from seamless.midlevel.serialize import extract
topology, _, _, _, _ = extract(*ctx2._graph[:2])
import json
json.dump(topology, open("context2-graph.json", "w"), sort_keys=True, indent=2)
f = open("context2-graph-raw.txt", "w")
from pprint import pprint
pprint(ctx2._graph[0], stream=f)

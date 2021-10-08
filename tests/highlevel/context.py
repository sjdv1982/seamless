from seamless.highlevel import Context
import json

ctx = Context()

ctx.a = 12

def triple_it(a):
    print("triple", a)
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.transform.debug.direct_print = True
ctx.myresult = ctx.transform
ctx.compute()
print(ctx.myresult.value)

ctx2 = Context()
ctx2.sub = ctx
ctx2.sub.transform.debug.direct_print = True
ctx2.sub2 = ctx
ctx2.sub2.transform.debug.direct_print = True
ctx2.translate()
print(ctx2.sub.myresult.value)
ctx2.compute()
print(ctx2.sub.myresult.value)

ctx2.sub.a = 3
ctx2.sub2.a = 5
ctx2.compute()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)

graph = ctx.get_graph()
j = json.dumps(graph, sort_keys=True, indent=2)
from seamless import get_hash
print(get_hash(j).hex())

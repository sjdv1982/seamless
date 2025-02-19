import seamless

seamless.delegate(False)

from seamless.workflow import Context
import json

ctx = Context()

ctx.a = 12


def triple_it(a, b):
    print("3 * a + b, a = %s, b = %s" % (a, b))
    return 3 * a + b


ctx.transform = triple_it
ctx.transform.debug.direct_print = True
ctx.transform.a = ctx.a
ctx.transform.b = 6
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
from seamless import Buffer

print(Buffer(j.encode()).get_checksum().hex())

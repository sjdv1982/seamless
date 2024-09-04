import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell

ctx = Context()
ctx.add = lambda a, b: a + b
ctx.a = 10
ctx.b = 20
ctx.add.a = ctx.a
ctx.add.b = ctx.b
ctx.result = ctx.add
ctx.compute()
print(ctx.result.value)
print()

subctx = ctx
ctx = Context()
ctx.sub1 = subctx
ctx.compute()
print(ctx.sub1.result.value)
ctx.sub2 = subctx
ctx.compute()
print(ctx.sub2.result.value)
ctx.sub3 = ctx.sub1
ctx.compute()
print(ctx.sub3.result.value)
print()
subctx.add.code = lambda a, b: a * b
ctx.a1 = 110
ctx.a2 = 210
ctx.sub1.a = ctx.a1
ctx.sub2.a = ctx.a2
subctx.compute()
ctx.compute()
print(subctx.result.value)
print(ctx.sub1.result.value)
print(ctx.sub2.result.value)
print(ctx.sub3.result.value)
print()

ctx.sub = Context()
ctx.sub.sub1 = subctx
ctx.sub.sub2 = ctx.sub2
ctx.sub.sub2.a = ctx.a1
ctx.sub.sub3 = ctx.sub.sub1
ctx.sub.sub3.a = ctx.a1
ctx.compute()
print(ctx.sub.sub1.result.value)
print(ctx.sub.sub2.result.value)
print(ctx.sub.sub3.result.value)
print()
from pprint import pprint

pprint(ctx.status)

# Copying subcontexts does not copy external connections
ctx.subc = Context()
ctx.subc.a = Cell("int")
ctx.subc.a = ctx.a1
ctx.subc2 = ctx.subc
ctx.compute()
print(ctx.subc.a.value)
print(ctx.subc2.a.value)  # None!
ctx.a1 = 1000
ctx.compute()
print(ctx.subc.a.value)
print(ctx.subc2.a.value)  # None!
print()

graph = ctx.get_graph()
ctx2 = Context()
ctx2.graph = graph
ctx2.graph.celltype = "plain"
###ctx2.graph.mount("/tmp/graph.json", persistent=True)
ctx2.compute()

ctx3 = Context()
ctx3.z = Cell()
ctx3.compute()
print(ctx3.status)

ctx4 = Context()
ctx4.sub = ctx3
ctx4.zz = 10
ctx4.sub.z = ctx4.zz
ctx4.compute()
ctx4.sub2 = ctx4.sub
ctx4.sub2.sub3 = ctx4.sub
ctx4.compute()
print(ctx4.status)

ctx2.graph = ctx4.get_graph()
ctx2.compute()

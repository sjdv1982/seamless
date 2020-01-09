from seamless.highlevel import Context
import json

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
ctx.compute()
print(ctx.myresult.value)

ctx2 = Context()
ctx2.sub = ctx
ctx2.sub2 = ctx
print(ctx2.sub.myresult.value)
ctx2.compute()
print(ctx2.sub.myresult.value)

ctx2.sub.a = 3
ctx2.sub2.a = 5
ctx2.compute()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)

graph = ctx.get_graph()
json.dump(graph, open("context2-graph.json", "w"), sort_keys=True, indent=2)

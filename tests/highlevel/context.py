from seamless.highlevel import Context
import json

ctx = Context()
ctx.mount("/tmp/mount-test")

ctx.a = 12

def triple_it(a):
    print("triple", a)
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
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

graph = ctx.get_graph()
json.dump(graph, open("context-graph.json", "w"), sort_keys=True, indent=2)

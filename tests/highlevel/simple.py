from seamless.highlevel import Context
import json

# 0
ctx = Context()
ctx.mount("/tmp/mount-test")

# 1
ctx.a = 10
ctx.translate()
print(ctx.a.value)

# 1a
ctx.a = 12
ctx.translate()
print(ctx.a.value)

# 2
def double_it(a):
    return 2 * a

ctx.transform = double_it
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)

# 3
ctx.a = 12
ctx.equilibrate()
print(ctx.myresult.value)
raise NotImplementedError # should be 24, not None!

# 4
def triple_it(a):
    return 3 * a
ctx.transform.code = triple_it
ctx.equilibrate()
print(ctx.myresult.value)

# 5
ctx.tfcode >> ctx.transform.code
ctx.transform.b = 100
def triple_it2(a, b):
    return 3 * a + b
ctx.tfcode = triple_it2
ctx.equilibrate()
print(ctx.myresult.value)

# 6
ctx.translate(force=True)
ctx.equilibrate()
print(ctx.myresult.value)

graph = ctx.get_graph()
json.dump(graph, open("simple-graph.json", "w"), sort_keys=True, indent=2)

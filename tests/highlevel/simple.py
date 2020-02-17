from seamless.highlevel import Context
import json

# 0
ctx = Context()
### ctx.mount("/tmp/mount-test")  # not implemented, maybe never

# 1
ctx.a = 10
ctx.a.celltype = "int"
ctx.translate()
print("1", ctx.a.value)

# 1a
ctx.a = 12
ctx.translate()
print("1a", ctx.a.value)

# 2
def double_it(a):
    return 2 * a

ctx.transform = double_it
###ctx.transform.hash_pattern = {"*": "#"}
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.myresult.celltype = "int"
ctx.compute()
print("2", ctx.myresult.value)

# 3
ctx.a = 12
ctx.compute()
print("3", ctx.myresult.value)

# 4
def triple_it(a):
    return 3 * a
ctx.transform.code = triple_it
ctx.compute()
print("4", ctx.myresult.value)

# 5
ctx.tfcode >> ctx.transform.code
def triple_it2(a, b):
    return 3 * a + b
ctx.tfcode = triple_it2
ctx.translate()
print("5 (should be None)", ctx.myresult.value)

# 6
ctx.transform.b = 100
ctx.compute()
print("6", ctx.myresult.value)

# 6a
ctx.translate(force=True)
ctx.compute()
print("6a", ctx.myresult.value)

graph = ctx.get_graph()
json.dump(graph, open("simple-graph.json", "w"), sort_keys=True, indent=2)

inp = ctx.transform.inp
print(inp.data)
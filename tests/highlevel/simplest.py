from seamless.highlevel import Context, Cell
from pprint import pprint

ctx = Context()
ctx.mount("/tmp/mount-test")

ctx.a = 0
ctx.translate()
ctx.a = 2
ctx.get_graph()
print(ctx.a.schema)
print(ctx.a.value)
print(ctx.a.exception)

ctx.a = 1
ctx.a.example = 0
ctx.compute()
print(ctx.a.schema)
print(ctx.a.value)

ctx.a = Cell()
ctx.compute()
print(ctx.a.schema)
print(ctx.a.value)

ctx.a.example = 50
print(ctx.a.value)
print(ctx.a.schema)
ctx.a.set(12)

ctx.compute()
print(ctx.a.value)

ctx.a = 1.2
ctx.compute()
print(ctx.a.exception)
print(ctx.a.value)
print(ctx.a.schema)

del ctx.a
ctx.a = "test"
ctx.a.example = "test"
ctx.compute()
print(ctx.a.value)
print(ctx.a.schema)

ctx.translate(force=True)
ctx.compute()
print(ctx.a.value)
print(ctx.a.schema)

graph = ctx.get_graph()
pprint(graph)

def validation(self):
    print("RUN VALIDATION", self)
    assert self != "test"

ctx.a.add_validator(validation)
ctx.compute()
print(ctx.a.schema)
print()
print("simplest.py EXCEPTION:")
print(ctx.a.exception)
print("/simplest.py EXCEPTION")
print()
graph = ctx.get_graph()
pprint(graph)

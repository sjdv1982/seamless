import json
from seamless.highlevel import Context, Cell, DeepCell
ctx = Context()
ctx.a = DeepCell()
print(ctx.a)
#ctx.a.set({"test": 1, "test2": 2})  # possible, but against the spirit of deep cells
ctx.a.test = 1
ctx.a.test2 = 2
print(json.dumps(ctx.a._get_hcell(), sort_keys=True))
ctx.compute()
ctx.a.test3.set(20)
ctx.a.test4 = 55
ctx.compute()
print(ctx.a)
print(ctx.a.data)
print(ctx.a._get_cell().value)
print(ctx.a.data["test2"], ctx.resolve(ctx.a.data["test2"], "mixed"))

ctx.a2 = ctx.a
ctx.compute()
print(ctx.a2.value)

ctx.a3 = DeepCell()
ctx.a3 = ctx.a
ctx.compute()
print(ctx.a3.data)

ctx.test = Cell("int")
ctx.test = ctx.a3.test4
ctx.compute()
print(ctx.test.value)

'''
ctx.a = {"test": 1, "test2": 2}
ctx.compute()
print(ctx.a._data)
print(ctx.a._get_cell().value)
print(ctx.a._get_cell().hash_pattern)
print(ctx.a.data)
print(ctx.a.value)
print(ctx.a.value.unsilk)
print(ctx.a.value.test)

print()
ctx.a.set({"test3": 10, "test4": 11})
ctx.compute()
print(ctx.a.data)
print(ctx.a.value)
print(ctx.a.value.unsilk)
print(ctx.a.value.test4)
'''
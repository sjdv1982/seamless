import json
from seamless.highlevel import Context, DeepCell
ctx = Context()
ctx.a = DeepCell()
print(ctx.a)
ctx.a.set({"test": 1, "test2": 2})
ctx.compute()
print(ctx.a)
print(ctx.a._get_cell().data)
print(ctx.a._get_cell().value)
print(ctx.a.data)
print(ctx.a.value)
'''
ctx.a = {"test": 1, "test2": 2}
print(json.dumps(ctx.a._get_hcell(), sort_keys=True))
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
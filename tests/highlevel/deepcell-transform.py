from seamless.highlevel import Context, Cell, SimpleDeepCell, DeepCell
from seamless.core.protocol.json import json_dumps
ctx = Context()
#ctx.d = DeepCell()
#ctx.translate()
#or:
ctx.d = SimpleDeepCell()
ctx.d.set({"a":102, "b": 103})
ctx.compute()
def func(d):
    result = {}
    for k, v in d.items():
        result[k] = v + 1000
    return result
ctx.func = func
print(ctx.func.pins.d.value)
ctx.func.d = ctx.d
print(ctx.func.pins.d.value)
ctx.result = DeepCell()
ctx.result = ctx.func.result
ctx.compute()
transformation = ctx.resolve(ctx.func.get_transformation(), "plain")
print(json_dumps(transformation))
print(ctx.d.data) 
print(ctx.d.checksum)
print(transformation["d"][2])
print()
print(ctx.func.result.data)
print(ctx.result.data)
print(ctx.func.result.checksum)
print(ctx.result.checksum)
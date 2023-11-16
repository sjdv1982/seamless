import seamless
seamless.delegate(False)

from seamless.core import context, cell, StructuredCell
from seamless.core.protocol.deep_structure import DeepStructureError
import traceback

ctx = context(toplevel=True)
ctx.data = cell("mixed")
hash_pattern = {"*":"#"}
ctx.data._hash_pattern = hash_pattern
ctx.sc = StructuredCell(
    data=ctx.data,
    hash_pattern=hash_pattern
)

data = ctx.sc.handle
try:
    data.set(20)
except DeepStructureError:
    traceback.print_exc()
data.set({})

ctx.compute()
print(ctx.data.value)
print(data)
print(ctx.sc.value)

print("START")    
data.x = "test"
data.y = "test2"
data.z = "test3"

ctx.compute()
print(ctx.data.value)
print(data)
print(ctx.sc.value)
print(ctx.sc.data)

print(data["x"], data["y"], data["z"])
print(data.x.unsilk, data.y.unsilk, data.z.unsilk)

data.set({
    "p": 10,
    "q": 20,
    "r": 30
})
ctx.compute()
print(ctx.data.value)
print(data)
print(ctx.sc.value)

print(data.p.data, data.q.data, data.r.data)

print("STOP")
import sys; sys.exit()

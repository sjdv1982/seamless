import seamless
seamless.delegate(False)

from seamless.workflow.core import context, cell, StructuredCell
from seamless.workflow.core.protocol.deep_structure import DeepStructureError
import traceback

ctx = context(toplevel=True)
ctx.data = cell("mixed")
hash_pattern = {"*":"##"}
ctx.data._hash_pattern = hash_pattern
ctx.sc = StructuredCell(
    data=ctx.data,
    hash_pattern=hash_pattern
)

data = ctx.sc.handle
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

print("START2")
data.x = b'BUF'
data.y = b'BUF2\n'
data.z = b'42\n'
data.p = b'\x89PNG\r\n\x1a\n\x00\x00'
import numpy as np
data.q = np.arange(115,120,dtype=np.uint8)
data.r = np.array(b"TEST!",ndmin=1)

ctx.compute()
print(ctx.data.value)
for k in sorted(ctx.data.value.keys()):
    print(k, ctx._manager.resolve(ctx.sc.data[k]))

print()
print(ctx.sc.value)
data = ctx.sc.handle
print(data.x.unsilk, type(data.x.unsilk), data.y.unsilk, type(data.y.unsilk), data.z.unsilk, type(data.z.unsilk))
print(data.p.unsilk, type(data.p.unsilk))
print(data.q.unsilk, type(data.q.unsilk))
print(data.r.unsilk, type(data.r.unsilk))

print("STOP")
import sys; sys.exit()

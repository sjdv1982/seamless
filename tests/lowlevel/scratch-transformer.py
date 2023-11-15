import seamless
from seamless.core import context, cell, transformer

seamless.delegate(level=3)

ctx = context(toplevel=True)
ctx.a = cell("float")
ctx.b = cell("float")
ctx.c = cell("float")

ctx.a.set(120)
ctx.b.set(130)
ctx.c.set(140)
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
print(ctx.a.checksum, ctx.b.checksum, ctx.c.checksum)

ctx.code = cell("transformer").set('a + b + c')
ctx.result = cell("float")
ctx.result._scratch = True
ctx.tf = transformer({
    "a": ("input", "float"),
    "b": ("input", "float"),
    "c": ("input", "float"),
    "result": ("output", "float"),
})
ctx.tf._scratch = True
ctx.code.connect(ctx.tf.code)
ctx.a.connect(ctx.tf.a)
ctx.b.connect(ctx.tf.b)
ctx.c.connect(ctx.tf.c)
ctx.tf.result.connect(ctx.result)
ctx.compute()
print(ctx.result.checksum)
print(ctx.result.value)

from seamless.core.cache.buffer_remote import _write_server
import requests
requests.put(_write_server + "/B:AHAH", "X")
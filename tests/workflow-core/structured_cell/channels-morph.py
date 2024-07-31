# adapted from simple-channels.py
import seamless
seamless.delegate(False)

from seamless.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.upstream = cell("int")

ctx.sc_auth = cell("mixed")
ctx.sc_buffer = cell("mixed")
ctx.sc_data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.sc_data,
    auth=ctx.sc_auth,
    buffer=ctx.sc_buffer,
    inchannels=[("a",)],
    outchannels=[("a",), ("b",), ("c",)],
)
ctx.a = cell("int")
ctx.sc.outchannels[("a",)].connect(ctx.a)
ctx.b = cell("mixed")
ctx.sc.outchannels[("b",)].connect(ctx.b)
ctx.c = cell("mixed")
ctx.sc.outchannels[("c",)].connect(ctx.c)


ctx.upstream.connect(ctx.sc.inchannels[("a"),])
ctx.upstream.set(10)
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.sc.set({"b": 20, "c": 30})
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.upstream.set(11)
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.sc.set({"b": 21, "c": 31})
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
print("STOP"); import sys; sys.exit()

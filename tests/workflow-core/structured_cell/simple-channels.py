import seamless
seamless.delegate(False)

from seamless.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[()],
    outchannels=[("a",), ("b",), ("c",)]
)

ctx.a = cell("int")
ctx.sc.outchannels[("a",)].connect(ctx.a)
ctx.b = cell("mixed")
ctx.sc.outchannels[("b",)].connect(ctx.b)
ctx.c = cell("mixed")
ctx.sc.outchannels[("c",)].connect(ctx.c)

ctx.upstream = cell("mixed").set({"a": 1})
ctx.upstream.connect(ctx.sc.inchannels[()])

ctx.compute()
print(ctx.a.status, ctx.b.status, ctx.c.status, ctx.a.value, ctx.b.value, ctx.c.value)
ctx.upstream.set({"a": 10, "b": {"x": 20}, "c": [1,2,3]})
ctx.compute()
print(ctx.a.status, ctx.b.status, ctx.c.status, ctx.a.value, ctx.b.value, ctx.c.value)
text = ["*" * 1000]
ctx.upstream.set({"a": text.copy(), "b": text.copy(), "c": text.copy()})
ctx.compute()
print(ctx.a.checksum, ctx.b.checksum, ctx.c.checksum)
print(ctx.a.status, ctx.b.status, ctx.c.status)
print(ctx.a.exception)

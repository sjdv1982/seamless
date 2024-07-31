import seamless
from seamless.core import context, cell, StructuredCell

seamless.delegate(level=3)

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.data._scratch = True
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[("a",), ("b",), ("c",)],
)
ctx.a = cell("bytes")
ctx.a.connect(ctx.sc.inchannels[("a",)])
ctx.b = cell("bytes")
ctx.b.connect(ctx.sc.inchannels[("b",)])
ctx.c = cell("bytes")
ctx.c.connect(ctx.sc.inchannels[("c",)])

ctx.a.set("this is text 1 " * 4)
ctx.b.set("this is text 2 " * 4)
ctx.c.set("this is text 3 " * 4)
ctx.compute()
print(ctx.a.value[:20], ctx.b.value[:20], ctx.c.value[:20])
print(ctx.data.checksum)
print(ctx.data.value)

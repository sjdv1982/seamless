import seamless
from seamless.core import context, cell, StructuredCell

seamless.delegate(level=3)

ctx = context(toplevel=True)
ctx.data = cell("mixed", hash_pattern={"*": "##"})
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[("a",), ("b",), ("c",)],
    outchannels=[()],
    hash_pattern={"*": "##"}
)
ctx.a = cell("bytes")
ctx.a.connect(ctx.sc.inchannels[("a",)])
ctx.b = cell("bytes")
ctx.b.connect(ctx.sc.inchannels[("b",)])
ctx.c = cell("bytes")
ctx.c.connect(ctx.sc.inchannels[("c",)])
ctx.result = cell("mixed")
ctx.result._scratch = True
ctx.sc.outchannels[()].connect(ctx.result)

ctx.a.set("First text " * 1000)
ctx.b.set("Second text " * 1000)
ctx.c.set("Third text " * 1000)
ctx.compute()
print(ctx.a.value[:20], ctx.b.value[:20], ctx.c.value[:20])
print(ctx.a.checksum, ctx.b.checksum, ctx.c.checksum)
print(ctx.data.checksum, ctx.data.buffer)
print(ctx.result.checksum)
v = ctx.result.value
print(v["a"][:20], v["b"][:20], v["c"][:20])

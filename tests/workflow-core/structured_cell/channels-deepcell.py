# adapted from simple-channels.py
import seamless

seamless.delegate(False)

from seamless.workflow.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed", hash_pattern={"*": "#"})
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[()],
    outchannels=[("a",), ("b",), ("c",)],
    hash_pattern={"*": "#"},
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
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.upstream.set({"a": 10, "b": {"x": 20}, "c": [1, 2, 3]})
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)

# Take 2, make upstream a deep cell now instead of sc
ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[()],
    outchannels=[("a",), ("b",), ("c",)],
)
ctx.a = cell("int")
ctx.sc.outchannels[("a",)].connect(ctx.a)
ctx.b = cell("mixed")
ctx.sc.outchannels[("b",)].connect(ctx.b)
ctx.c = cell("mixed")
ctx.sc.outchannels[("c",)].connect(ctx.c)

ctx.upstream = cell("mixed", hash_pattern={"*": "#"}).set({"a": 1})
ctx.upstream.connect(ctx.sc.inchannels[()])

ctx.compute()
print(ctx.data.value)
print(ctx.a.value, ctx.b.value, ctx.c.value)
ctx.upstream.set({"a": 10, "b": {"x": 20}, "c": [1, 2, 3]})
ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)

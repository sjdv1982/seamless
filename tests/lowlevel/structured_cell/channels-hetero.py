from seamless.core import context, cell, StructuredCell

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[("codefield",)],
    outchannels=[()]
)


ctx.upstream = cell("python").set("print(42)")
ctx.upstream.connect(ctx.sc.inchannels[("codefield",)])

ctx.compute()
print(ctx.data.value)
ctx.upstream.set("""
print(43)
print(44)
""")
ctx.compute()
print(ctx.data.value)
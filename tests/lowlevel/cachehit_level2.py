from seamless.core import cell, transformer, context
ctx = context(toplevel=True)
ctx.cell1 = cell("cson").set("a: 10")
ctx.cell1a = cell("plain")
ctx.cell1.connect(ctx.cell1a)

#params = {"a": "input"}
print(ctx.cell1.value)
print(ctx.cell1a.value)

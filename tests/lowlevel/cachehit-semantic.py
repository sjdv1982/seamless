import seamless
seamless.delegate(False)

from seamless.core import cell, transformer, context
ctx = context(toplevel=True)
ctx.cell1 = cell("cson").set("a: 10")
ctx.cell1a = cell("plain")
ctx.cell1.connect(ctx.cell1a)
ctx.compute()

print(ctx.cell1.value)
print(ctx.cell1.semantic_checksum)
print(ctx.cell1a.value)
print(ctx.cell1a.semantic_checksum)

params = {
    "v": ("input", "plain"), 
    "result": "output"
}
def func(v):
    return v["a"] + 2
ctx.code = cell("transformer").set(func)
ctx.tf = transformer(params)
ctx.code.connect(ctx.tf.code)
ctx.cell1.connect(ctx.tf.v)
ctx.result = cell()
ctx.tf.result.connect(ctx.result)
ctx.compute()
print(ctx.result.value)

seamless.set_ncores(0) # no more local computations
ctx.ttf = transformer(params)
ctx.code.connect(ctx.ttf.code)
ctx.cell1a.connect(ctx.ttf.v)
ctx.result2 = cell()
ctx.ttf.result.connect(ctx.result2)
ctx.compute()
print(ctx.result2.value)

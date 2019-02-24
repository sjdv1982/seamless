import seamless
from seamless.core import cell, transformer, context
ctx = context(toplevel=True)
ctx.cell1 = cell("cson").set("a: 10")
ctx.cell1a = cell("plain")
ctx.cell1.connect(ctx.cell1a)

print(ctx.cell1.value)
print(ctx.cell1.semantic_checksum)
print(ctx.cell1a.value)
print(ctx.cell1a.semantic_checksum)

params = {"v": "input", "result": "output"}
def func(v):
    return v["a"] + 2
ctx.code = cell("transformer").set(func)
ctx.tf = transformer(params)
ctx.code.connect(ctx.tf.code)
ctx.cell1.connect(ctx.tf.v)
ctx.result = cell()
ctx.tf.result.connect(ctx.result)
ctx.equilibrate()
print(ctx.result.value)

tcache = ctx._get_manager().transform_cache
tf1 = tcache.transformer_to_level1[ctx.tf]
print("TF level 1", tf1.get_hash())
tf2 = tcache.hlevel1_to_level2[tf1.get_hash()]
print("TF level 2", tf2.get_hash())

seamless.set_ncores(0) # no more local computations
ctx.ttf = transformer(params)
ctx.code.connect(ctx.ttf.code)
ctx.cell1a.connect(ctx.ttf.v)
ctx.result2 = cell()
ctx.ttf.result.connect(ctx.result2)
ctx.equilibrate()
print(ctx.result2.value)

ttf1 = tcache.transformer_to_level1[ctx.ttf]
print("TTF level 1", ttf1.get_hash())
ttf2 = tcache.hlevel1_to_level2[ttf1.get_hash()]
print("TTF level 2", ttf2.get_hash())

assert ttf2.get_hash() == tf2.get_hash()
import seamless
seamless.delegate(False)

from seamless.workflow import Context, Cell
from seamless.stdlib import map

print(str(map.map_list.help.value)[:30])

ctx = Context()
ctx.inp = Cell("mixed")
ctx.inp0 = Cell()
ctx.inp0 = ctx.inp
ctx.uniform = Cell("mixed")
ctx.add = lambda a,b,c: a+b+c
ctx.add.a = ctx.inp0.a
ctx.add.b = ctx.inp0.b
ctx.add.c = ctx.uniform
ctx.result = Cell("mixed")
ctx.result = ctx.add
ctx.subc = Context()
ctx.subc.blah = 1000
ctx.compute()

mapped_ctx = ctx

ctx = Context()
ctx.include(map.map_list)
print(str(ctx.lib.map_list.help.value)[:30])

ctx.inp1 = {"a": 10, "b": 20}
ctx.inp2 = {"a": -80, "b": 30}
ctx.inp3 = {"a": -20, "b": 90}
ctx.inp = Cell()
ctx.inp[0] = ctx.inp1
ctx.inp[1] = ctx.inp2
ctx.inp[2] = ctx.inp3
ctx.inp_mixed = ctx.inp
ctx.inp_mixed.celltype = "mixed"
ctx.uniform = 1000
ctx.result = Cell("mixed")
ctx.mapped_ctx = mapped_ctx
ctx.mapping = ctx.lib.map_list(
    context_graph=ctx.mapped_ctx,
    inp=ctx.inp_mixed,
    uniform=ctx.uniform,
    result=ctx.result
)
print(str(ctx.mapping.help.value)[:30])
ctx.compute()
print(str(ctx.mapping.help.value)[:30])
print(ctx.result.value)
ctx.inp1 = {"a": 0, "b": 1}
ctx.compute()
print(ctx.result.value)
del ctx.inp3
ctx.compute()
print(ctx.result.value)

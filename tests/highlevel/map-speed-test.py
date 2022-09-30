from seamless.highlevel import Context, Cell, DeepCell
from seamless.highlevel.stdlib import map

ctx1 = Context()
ctx1.inp = Cell("mixed")
ctx1.result = Cell("mixed").set(42)

ctx2 = Context()
ctx2.inp = Cell("mixed")
ctx2.inp0 = Cell()
ctx2.inp0 = ctx2.inp
ctx2.uniform = Cell("mixed")
ctx2.add = lambda a,b,c: a+b+c
ctx2.add.a = ctx2.inp0.a
ctx2.add.b = ctx2.inp0.b
ctx2.add.c = ctx2.uniform
ctx2.result = Cell("mixed")
ctx2.result = ctx2.add
ctx2.subc = Context()
ctx2.subc.blah = 1000
ctx2.compute()

ctx = Context()
ctx.include(map.map_dict)

ctx.inp0 = Cell("mixed")
ctx.inp = DeepCell()
ctx.inp = ctx.inp0
ctx.uniform = 1000
ctx.result = DeepCell()
ctx.mapped_ctx = Context()
ctx.keyorder = Cell("plain")
ctx.mapping = ctx.lib.map_dict(
    context_graph=ctx.mapped_ctx,
    inp=ctx.inp,
    uniform=ctx.uniform,
    result=ctx.result,
    keyorder=ctx.keyorder,
    elision=True,
    elision_chunksize=10,
)
ctx.result2 = Cell()
ctx.result2.hash_pattern = {"*": "#"}
ctx.result2 = ctx.result
ctx.compute()

import time
globcount = 0
def run(count):
    global globcount
    ctx.inp0.set({})
    old = globcount
    inp = {}
    for n in range(count):
        globcount += 1
        inp["k" + str(n+1)] = {"a": globcount, "b": globcount + 0.1}
    ctx.inp0.set(inp)
    t = time.time()
    ctx.compute(report=False)
    t2 = time.time() - t
    if ctx.result.checksum is not None and ctx.result2.checksum is not None:
        print(len(ctx.result.data.keys()))
        print(sum(ctx.result2.value.values()), count * (2*old + 1000 + 0.1) + 2 * count * (count/2+0.5))
    return t2

for mapped_ctx in ctx1, ctx2:
    ctx.mapped_ctx = mapped_ctx
    ctx.translate()
    for pcount in range(20):
        count = 2**pcount
        t=run(count)
        print("TIME", count, t)
        if t > 100 or t > 10: ###
            break

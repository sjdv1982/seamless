import seamless
from seamless.core import context, cell, transformer, unilink

try:
    redis_sink = seamless.RedisSink()
except Exception:
    pass

async def main():
    ctx = context(toplevel=True)
    ctx.cell1 = cell("int").set(1)
    ctx.cell2 = cell("int").set(2)
    #ctx.code = cell("transformer")
    #ctx.code = cell("transformer").set("c = 'test'")
    #ctx.code = cell("transformer").set("raise Exception")
    #ctx.code = cell("transformer").set("import time; time.sleep(2); c = a + b")
    ctx.code = cell("transformer").set("a + b")
    ctx.result = cell("int")
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1_unilink = unilink(ctx.cell1)
    ctx.cell1_unilink.connect(ctx.tf.a)    
    ctx.cell2.connect(ctx.tf.b)
    ctx.code_copy = cell("transformer")
    ctx.code.connect(ctx.code_copy)
    ctx.code_copy.connect(ctx.tf.code)
    ctx.result_unilink = unilink(ctx.result)
    ctx.tf.c.connect(ctx.result_unilink)
    ctx.result_copy = cell("int")
    ctx.result.connect(ctx.result_copy)
    await ctx.computation(1)
    print("STOP")
    print(ctx.cell1.value, ctx.cell1, ctx.cell1.status)
    print(ctx.cell2.value, ctx.cell2, ctx.cell2.status)
    print(ctx.code.value, ctx.code, ctx.code.status)
    print(ctx.code_copy.value, ctx.code_copy, ctx.code_copy.status)
    print(ctx.result.value, ctx.result, ctx.result.status)
    print(ctx.result_copy.value, ctx.result_copy, ctx.result_copy.status)
    print(ctx.tf.value, ctx.tf, ctx.tf.status)
    print(ctx.status)
    print(ctx.tf.exception)
    await ctx.computation()
    ctx.cell1.set(10)
    await ctx.computation()
    print(ctx.result.value, ctx.status)
    ctx.code.set("c = a + b + 1000")
    await ctx.computation()
    print(ctx.result.value, ctx.status)
    print("Introduce delay...")
    ctx.code.set("import time; time.sleep(2); c = -(a + b)")
    await ctx.computation(1.0)
    print("after 1.0 sec...")
    print(ctx.result.value, ctx.status)
    print("...")
    await ctx.computation()
    print(ctx.result.value, ctx.status)

import asyncio
asyncio.run(main())
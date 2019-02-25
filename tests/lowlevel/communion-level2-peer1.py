import seamless
from seamless.core import cell, transformer, context
from seamless import communionserver
communionserver.configure_servant(
    value=True, 
    transformer_result_level2=True
)
communionserver.configure_master(value=True)

redis_sink = seamless.RedisSink()

ctx = context(toplevel=True)
#ctx.cell1 = cell("cson").set("a: 10")
ctx.cell1 = cell("plain").set({'a': 10})

print(ctx.cell1.value)
print(ctx.cell1.semantic_checksum)

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

import asyncio
asyncio.get_event_loop().run_forever()
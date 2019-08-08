#import asyncio; asyncio.get_event_loop().set_debug(True)
import seamless
from seamless.core import context, cell, transformer, link

try:
    redis_sink = seamless.RedisSink()
except Exception:
    pass

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
ctx.cell1_link = link(ctx.cell1)
ctx.cell1_link.connect(ctx.tf.a)    
ctx.cell2.connect(ctx.tf.b)
ctx.code_copy = cell("transformer")
ctx.code.connect(ctx.code_copy)
ctx.code_copy.connect(ctx.tf.code)
ctx.result_link = link(ctx.result)
ctx.tf.c.connect(ctx.result_link)
ctx.result_copy = cell("int")
ctx.result.connect(ctx.result_copy)
ctx.equilibrate(1)
print("STOP")
print(ctx.cell1.value, ctx.cell1, ctx.cell1.status)
print(ctx.cell2.value, ctx.cell2, ctx.cell2.status)
print(ctx.code.value, ctx.code, ctx.code.status)
print(ctx.code_copy.value, ctx.code_copy, ctx.code_copy.status)
print(ctx.result.value, ctx.result, ctx.result.status)
print(ctx.result_copy.value, ctx.result_copy, ctx.result_copy.status)
print(ctx.tf.value, ctx.tf, ctx.tf.status)
print(ctx.status)
ctx.equilibrate()
ctx.cell1.set(10)
ctx.equilibrate()
print(ctx.result.value, ctx.status)
ctx.code.set("c = a + b + 1000")
ctx.equilibrate()
print(ctx.result.value, ctx.status)
print("Introduce delay...")
ctx.code.set("import time; time.sleep(2); c = -(a + b)")
ctx.equilibrate(1.0)
print("after 1.0 sec...")
print(ctx.result.value, ctx.status)
print("...")
ctx.equilibrate()
print(ctx.result.value, ctx.status)

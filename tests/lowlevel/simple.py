#import asyncio; asyncio.get_event_loop().set_debug(True)
import seamless
from seamless.core import context, cell, transformer, link

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
#ctx.code = cell("transformer").set("c = 'test'")
ctx.code = cell("transformer").set("raise Exception")
#ctx.code = cell("transformer").set("a + b")
ctx.result = cell("int")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_link = link(ctx.cell1)
ctx.cell1_link.connect(ctx.tf.a)    
ctx.cell2.connect(ctx.tf.b)
ctx.code.connect(ctx.tf.code)
ctx.result_link = link(ctx.result)
ctx.tf.c.connect(ctx.result_link)
ctx.result_copy = cell("int")
ctx.result.connect(ctx.result_copy)
ctx.equilibrate()
print("STOP")
print(ctx.cell1.value, ctx.cell1, ctx.cell1.status)
print(ctx.cell2.value, ctx.cell2, ctx.cell2.status)
print(ctx.code.value, ctx.code, ctx.code.status)
print(ctx.result.value, ctx.result, ctx.result.status)
print(ctx.tf.value, ctx.tf, ctx.tf.status)
print(ctx.status())
"""
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
"""
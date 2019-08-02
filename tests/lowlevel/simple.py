#import asyncio; asyncio.get_event_loop().set_debug(True)
import seamless
from seamless.core import context, cell, transformer, link

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
#ctx.code = cell("transformer").set("c = 'test'") #.set("a + b")
ctx.code = cell("transformer").set("raise Exception")
ctx.result = cell("int")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_link = link(ctx.cell1)
ctx.cell1_link.connect(ctx.tf.a)    
#ctx.cell2.connect(ctx.tf.b)
ctx.code.connect(ctx.tf.code)
ctx.result_link = link(ctx.result)
ctx.tf.c.connect(ctx.result_link) #memory leak; investigate!
ctx.result_copy = cell("int")
ctx.result.connect(ctx.result_copy)
ctx.equilibrate()
print("STOP")
print(ctx.cell1.value)
print(ctx.cell2.value)
print(ctx.code.value)
print(ctx.result.value, ctx.tf.status())
###print(ctx.result.value, ctx.status)
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
import seamless
from seamless.core import context, cell, transformer, pytransformercell, link
import numpy as np

ctx = context(toplevel=True)
x = np.arange(10)
y = np.log(x+1)
cell1 = cell("mixed").set({"x": x, "y": y, "z": [1,2,"test",[3,4]]})
cell1.mount("/tmp/mixedcell.mixed")
ctx.cell1 = cell1
print(ctx.cell1.storage)
print(ctx.cell1.form)
print(ctx.cell1.value)

ctx.cell2 = cell("mixed").set(80)    
ctx.result = cell("mixed")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_link = link(ctx.cell1)
ctx.cell1_link.connect(ctx.tf.a)    
ctx.cell2.connect(ctx.tf.b)
ctx.code = pytransformercell().set("c = a['x'] * a['y'] + b")
ctx.code.connect(ctx.tf.code)
ctx.result_link = link(ctx.result)
ctx.tf.c.connect(ctx.result_link)
ctx.result_copy = cell("mixed")
ctx.result.connect(ctx.result_copy)

print(ctx.cell1.value)
print(ctx.code.value)
ctx.equilibrate()
print(ctx.result.value, ctx.status)
ctx.cell2.set(10)
ctx.equilibrate()
print(ctx.result.value, ctx.status)
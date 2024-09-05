import seamless

seamless.delegate(False)

from seamless.workflow.core import context, cell, transformer, unilink
import numpy as np

ctx = context(toplevel=True)
x = np.arange(10)
y = np.log(x + 1)
cell1 = cell("mixed").set({"x": x, "y": y, "z": [1, 2, "test", [3, 4]]})
cell1.mount("/tmp/mixedcellsilk.mixed")
ctx.cell1 = cell1
ctx.compute()
print(ctx.cell1.value)
print(ctx.cell1.storage)
print(ctx.cell1.form)

ctx.cell2 = cell("mixed").set(80)
ctx.result = cell("mixed")
ctx.tf = transformer({"a": "input", "b": "input", "c": "output"})
ctx.cell1_unilink = unilink(ctx.cell1)
ctx.cell1_unilink.connect(ctx.tf.a)
ctx.cell2.connect(ctx.tf.b)
ctx.code = cell("transformer").set("c = a['x'] * a['y'] + b")
ctx.code.connect(ctx.tf.code)
ctx.result_unilink = unilink(ctx.result)
ctx.tf.c.connect(ctx.result_unilink)
ctx.result_copy = cell("mixed")
ctx.result.connect(ctx.result_copy)
ctx.compute()

print(ctx.cell1.value)
print(ctx.code.value)
ctx.compute()
print(ctx.result.value, ctx.status)
ctx.cell2.set(10)
ctx.compute()
print(ctx.result.value, ctx.status)

with open("/tmp/mixedcellsilk.mixed", "rb") as f:
    content = f.read()
from seamless import Buffer

print(Buffer(content).get_checksum().hex())

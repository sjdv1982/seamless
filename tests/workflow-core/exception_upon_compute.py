import seamless
seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer, unilink
import sys

code = "print('TEST'); raise Exception(a)"
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "output",
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.tf.code.set(code)
    ctx.tf.b.cell()
    ctx.tf.b.connect(ctx.result)
ctx.compute()
print(ctx.status)
print(ctx.tf.exception)
ctx.tf.code.set("'OK'")
ctx.compute()
print(ctx.status)
print(ctx.tf.exception)
print(ctx.result.value)

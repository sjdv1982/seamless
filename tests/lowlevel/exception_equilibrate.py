import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, link
import sys

code = "raise Exception(a)"
if len(sys.argv) == 2 and sys.argv[1] == "1":
    code = "result = a"
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
ctx.compute(5)
print(ctx.status)
print(ctx.tf.exception)
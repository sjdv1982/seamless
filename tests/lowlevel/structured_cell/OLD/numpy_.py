import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell
import numpy as np

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.mount("/tmp/mount-test", persistent=None) #directory remains, but empty

    ctx.inp_struc = context(toplevel=False)
    ctx.inp_struc.data = cell("mixed")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        plain = False,
        schema = None,
        buffer = None,
        inchannels = None,
        outchannels = [("a",), ("b",), ("data",)]
    )
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "data": "input",
        "c": "output"
    })

    ctx.inp.outchannels["a"].connect(ctx.tf.a)
    ctx.inp.outchannels["b"].connect(ctx.tf.b)
    ctx.inp.outchannels["data"].connect(ctx.tf.data)
    ctx.tf.code.cell().set("c = a * data + b")

    ctx.result = cell("array")
    #ctx.result.mount(persistent=True)
    ctx.tf.c.connect(ctx.result)


ctx.equilibrate()
print(ctx.tf.status)
print(ctx.result.value)

inp = ctx.inp.handle
inp["a"] = 10
inp["b"] = 12
inp["data"] = np.arange(100)

ctx.equilibrate()
print(ctx.tf.status)

print(ctx.result.value)

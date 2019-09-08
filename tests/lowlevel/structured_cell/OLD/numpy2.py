raise NotImplementedError  # Silk access is not working; the modified code below kludges around it

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
        outchannels = [()]
    )
    ctx.tf = transformer({
        ###"inp": ("input", "copy", "silk"),
        "inp": ("input", "copy", "mixed"),
        "c": "output",
    })

    ctx.inp.outchannels[()].connect(ctx.tf.inp)
    ###ctx.tf.code.cell().set("c = inp.a * inp.dat + inp.b")
    ctx.tf.code.cell().set("c = inp['a'] * inp['dat'] + inp['b']")

    ctx.result = cell("array")
    ctx.tf.c.connect(ctx.result)

ctx.equilibrate()
print(ctx.tf.status)
print(ctx.result.value)

inp = ctx.inp.handle
inp["a"] = 10
inp["b"] = 12
print("INP", inp)
#ctx.equilibrate() ###gives error in transformer, until next line
inp["dat"] = np.arange(100)

ctx.equilibrate()
print(ctx.tf.status)

print(ctx.result.value)

#shell = ctx.tf.shell()

import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell
import numpy as np

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.inp_struc = context(name="inp_struc",context=ctx)
    ctx.inp_struc.storage = cell("text")
    ctx.inp_struc.form = cell("json")
    ctx.inp_struc.data = cell("mixed",
        form_cell = ctx.inp_struc.form,
        storage_cell = ctx.inp_struc.storage,
    )
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = ctx.inp_struc.storage,
        form = ctx.inp_struc.form,
        schema = None,
        buffer = None,
        inchannels = None,
        outchannels = [()]
    )
    ctx.tf = transformer({
        "inp": ("input", "copy", "silk"),
        "c": "output",
    })

    ctx.inp.connect_outchannel((), ctx.tf.inp)
    ctx.tf.code.cell().set("c = inp.a * inp.dat + inp.b")

    ctx.result = cell("mixed")
    ctx.tf.c.connect(ctx.result)

    ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.tf.status())
print(ctx.result.value)

inp = ctx.inp.handle
inp["a"] = 10
inp["b"] = 12
print("INP", inp)
#ctx.equilibrate() ###gives error in transformer, until next line
inp["dat"] = np.arange(100)

ctx.equilibrate()
print(ctx.tf.status())

print(ctx.result.value)

#shell = ctx.tf.shell()

import seamless
from seamless.core.macro import macro_mode_on
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
    ctx.inp_struc.schema = cell("json")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = ctx.inp_struc.storage,
        form = ctx.inp_struc.form,
        schema = ctx.inp_struc.schema,
        buffer = None,
        inchannels = [("a",)],
        outchannels = [()]
    )
    ctx.a = cell("json")
    ctx.inp.connect_inchannel(ctx.a, ("a",))

    ctx.tf = transformer({
        "inp": ("input", "copy", "silk"),
        "c": "output",
    })

    ctx.inp.connect_outchannel((), ctx.tf.inp)
    ctx.tf.code.cell().set("c = inp.a.x * inp.dat + inp.b")

    ctx.result = cell()
    ctx.tf.c.connect(ctx.result)

    ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.tf.status())
print(ctx.result.value)

inp = ctx.inp.handle
#inp.a = {"x": 10}
inp.b = 100
inp.a.x = 11
#ctx.equilibrate() ###gives error in transformer, until next line
inp.dat = np.arange(10)
print(inp, type(inp.a))

ctx.equilibrate()
print(ctx.tf.status())

print(ctx.result.value)

print(ctx.inp.value)
print(inp.schema, inp)
ctx.a.set({"x": 12})
print("START")
ctx.a.set(1) #error
ctx.equilibrate()
print(ctx.inp.value)
print(ctx.result.value)
ctx.a.set({"x": 22})
ctx.equilibrate()
print(ctx.inp.value)
print(ctx.result.value)
#shell = ctx.tf.shell()

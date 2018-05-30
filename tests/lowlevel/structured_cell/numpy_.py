import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell
import numpy as np

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.inp_struc = context(name="inp_struc",context=ctx)
    ctx.inp_struc.data = cell("mixed")
    ctx.inp_struc.storage = cell("json")
    ctx.inp_struc.form = cell("json")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = ctx.inp_struc.storage,
        form = ctx.inp_struc.form,
        schema = None,
        inchannels = None,
        outchannels = [("a",), ("b",), ("data",)]
    )
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "data": "input",
        "c": "output"
    })

    #ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.result.value)

a = ctx.a.monitor
a.set_path((), {})
aa = a.get_data()
aa.a = 10
aa.b = 20
aa.data = np.

#shell = ctx.tf.shell()

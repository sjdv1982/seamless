import seamless
from seamless import Silk
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
    ctx.inp_struc.schema = cell("json")
    ctx.inp = StructuredCell(
        "inp",
        ctx.inp_struc.data,
        storage = ctx.inp_struc.storage,
        form = ctx.inp_struc.form,
        schema = ctx.inp_struc.schema,
        buffer = None,
        inchannels = [],
        outchannels = [()]
    )

    ctx.tf = transformer({
        "inp": ("input", "copy", "silk"),
        "c": "output",
    })

    ctx.inp.connect_outchannel((), ctx.tf.inp)
    ctx.tf.code.cell().set("c = inp.a.x * inp.dat + inp.b")

    ctx.result = cell()
    ctx.tf.c.connect(ctx.result)

inp = ctx.inp.handle

inp.a.set({"x": 2})
inp.dat.set(20)
inp.b.set(30)

ctx.equilibrate()
print(ctx.tf.status())
print(ctx.result.value)

def validate(self):
    print("validate")
    assert self.dat < self.b
inp.add_validator(validate)

schema = ctx.inp.handle.schema
example = Silk(
 schema=schema,
 schema_dummy=True,
 schema_update_hook=ctx.inp.handle._schema_update_hook
)

with example.fork():
    example.b = 3
    example.dat = 1

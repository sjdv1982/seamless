import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.a = cell("json").set(2)
    ctx.b = cell("json").set(3)
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    }, service=True)
    ctx.tf.transformer.server = "file://simpler-remote.rqseamless"
    ctx.a.connect(ctx.tf.a)
    ctx.b.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.result_form = cell("text")
    ctx.result_storage = cell("json")
    ctx.result = cell("mixed", form_cell=ctx.result_form, storage_cell=ctx.result_storage)
    ctx.tf.c.connect(ctx.result)

ctx.equilibrate()

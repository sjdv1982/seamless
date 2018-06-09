import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, StructuredCell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.a = cell("json").set({"1": 2})
    ctx.b = cell("json").set(2)
    ctx.mount("/tmp/mount-test")

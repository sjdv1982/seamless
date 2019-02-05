from seamless.core import macro_mode, context, cell, macro
from seamless.core.macro_mode import macro_mode_on

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.macro = macro({
        "a": "ref",
    })
    ctx.a = cell().set(42)
    ctx.code = cell("macro").set("""
ctx.answer = cell().set(a)
ctx.tf = transformer({"test": "input"})
ctx.answer.connect(ctx.tf.test)
    """)
    ctx.a.connect(ctx.macro.a)
    ctx.code.connect(ctx.macro.code)
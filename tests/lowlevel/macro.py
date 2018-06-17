import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell().set(1)
    ctx.macro = macro({
        "param": "copy",
    })
    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = pytransformercell().set("""
ctx.a = cell().set(1000 + param)
ctx.b = cell().set(2000 + param)
if param > 1:
    ctx.c = cell().set(42)
""")
    ctx.macro_code.connect(ctx.macro.code)
    ctx.mount("/tmp/mount-test")
print(ctx.macro.gen_context)
ctx.equilibrate()
print(ctx.macro_gen_macro.a.value)
print(ctx.macro_gen_macro.b.value)
print(hasattr(ctx.macro_gen_macro, "c"))
ctx.param.set(2)
ctx.equilibrate()
# Note that ctx.macro_gen_macro is now a new context, and
#   any references to the old context are invalid
# But this is a concern for the high-level!
print(ctx.macro_gen_macro.a.value)
print(ctx.macro_gen_macro.b.value)
print(hasattr(ctx.macro_gen_macro, "c"))
print(ctx.macro_gen_macro.c.value)

shell = ctx.macro.shell()

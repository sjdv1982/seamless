import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell().set(1)
    ctx.macro = macro({
        "param": "copy",
    })
    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = pytransformercell().set("""
ctx.sub = context(context=ctx,name="sub")
ctx.a = cell().set(1000 + param)
ctx.b = cell().set(2000 + param)
ctx.result = cell()
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.a.connect(ctx.tf.a)
ctx.b.connect(ctx.tf.b)
ctx.code = cell("pytransformer").set('''
c = a + b
''')
ctx.code.connect(ctx.tf.code)
ctx.tf.c.connect(ctx.result)
if param > 1:
    ctx.d = cell().set(42)
    raise Exception("on purpose") #causes the macro reconstruction to fail; comment it out to make it succeed
""")
    ctx.macro_code.connect(ctx.macro.code)
    ctx.mount("/tmp/mount-test")
print(ctx.macro.gen_context)
import time; time.sleep(0.5) #doing this instead of equilibrate() will cause the result update to be delayed until macro reconstruction
# if the macro reconstruction fails, the result update will still be accepted
### ctx.equilibrate()
print(ctx.macro_gen_macro.a.value)
print(ctx.macro_gen_macro.b.value)
print(hasattr(ctx.macro_gen_macro, "c"))
print(ctx.macro_gen_macro.result.value) #None instead of 3002, unless you enable ctx.equilibrate above

ctx.param.set(2)
ctx.equilibrate()
# Note that ctx.macro_gen_macro is now a new context, and
#   any references to the old context are invalid
# But this is a concern for the high-level!

print(ctx.macro_gen_macro.a.value)
print(ctx.macro_gen_macro.b.value)
print(hasattr(ctx.macro_gen_macro, "d"))
if hasattr(ctx.macro_gen_macro, "d"):
    print(ctx.macro_gen_macro.d.value)
print(ctx.macro_gen_macro.result.value) #will never be None! 3002 if the reconstruction failed, 3004 if it succeeded

shell = ctx.macro.shell()

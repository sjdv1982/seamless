import seamless
seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer, macro

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.param = cell().set(1)

    ctx.mymacro = macro({
        "param": "plain",
    })

    ctx.param.connect(ctx.mymacro.param)
    def macro_code(ctx, param):
        ctx.sub = context()
        ctx.a = cell().set(1000 + param)
        ctx.b = cell().set(2000 + param)
        ctx.result = cell()
        ctx.tf = transformer({
            "a": "input",
            "b": "input",
            "c": "output"
        })
        ctx.tf._debug = {
            "direct_print" : True
        }
        ctx.a.connect(ctx.tf.a)
        ctx.b.connect(ctx.tf.b)
        ctx.code = cell("transformer").set("print('TRANSFORM'); import time; time.sleep(2); c = a + b")
        ctx.code.connect(ctx.tf.code)
        ctx.tf.c.connect(ctx.result)
        assert param != 999   # on purpose
        if param > 1:
            ctx.d = cell().set(42)
            # raise Exception("on purpose") #causes the macro reconstruction to fail
        pass # For some reason, comments at the end are not captured with inspect.get_source?

    ctx.macrocode = cell("macro").set(macro_code)
    ctx.macrocode.connect(ctx.mymacro.code)


print("START")
ctx.compute(1)
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(hasattr(ctx.mymacro.ctx, "d"))
print(ctx.mymacro.ctx.result.value) #None
ctx.compute()
print(ctx.mymacro.ctx.result.value) #3002

print("Change 0")
ctx.param.set(-10)
ctx.compute()
# Note that ctx.mymacro.ctx is now a new context, and
#   any old references to the old context are invalid
# But this is a concern for the high-level!

try:
    print(ctx.mymacro.ctx)
except AttributeError:
    print("ctx.mymacro.ctx is undefined")
else:
    print(ctx.mymacro.ctx.a.value)
    print(ctx.mymacro.ctx.b.value)
    print(ctx.mymacro.ctx.hasattr("d"))
    if ctx.mymacro.ctx.hasattr("d"):
        print(ctx.mymacro.ctx.d.value)
    print(ctx.mymacro.ctx.result.value)

print("Change 1")
ctx.param.set(2)
ctx.compute()
# Note that ctx.mymacro.ctx is now a new context, and
#   any old references to the old context are invalid
# But this is a concern for the high-level!

try:
    print(ctx.mymacro.ctx)
except AttributeError:
    print("ctx.mymacro.ctx is undefined")
else:
    print(ctx.mymacro.ctx.a.value)
    print(ctx.mymacro.ctx.b.value)
    print(ctx.mymacro.ctx.hasattr("d"))
    if ctx.mymacro.ctx.hasattr("d"):
        print(ctx.mymacro.ctx.d.value)
    print(ctx.mymacro.ctx.result.value)

print("Change 2")
ctx.macrocode.set(
    ctx.macrocode.value + "   "
)
ctx.compute() # Macro execution, because macros are not cached. But no transformation

try:
    ctx.mymacro.ctx
except AttributeError:
    pass

print("Change 3")
ctx.macrocode.set(
    ctx.macrocode.value.replace("# raise Exception", "raise Exception")
)
ctx.compute()

try:
    print(ctx.mymacro.ctx)
except AttributeError:
    print("ctx.mymacro.ctx is undefined")
else:
    print(ctx.mymacro.ctx.a.value)
    print(ctx.mymacro.ctx.b.value)
    print(ctx.mymacro.ctx.hasattr("d"))
    if ctx.mymacro.ctx.hasattr("d"):
        print(ctx.mymacro.ctx.d.value)
    print(ctx.mymacro.ctx.result.value)

print("Change 4")
ctx.macrocode.set(
    ctx.macrocode.value.replace("raise Exception", "#raise Exception")
)
ctx.compute()
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(ctx.mymacro.ctx.hasattr("d"))
if ctx.mymacro.ctx.hasattr("d"):
    print(ctx.mymacro.ctx.d.value)
print(ctx.mymacro.ctx.result.value)

print("Change 5")
ctx.param.set(0)
ctx.compute()
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(ctx.mymacro.ctx.hasattr("d"))
if ctx.mymacro.ctx.hasattr("d"):
    print(ctx.mymacro.ctx.d.value)
print(ctx.mymacro.ctx.result.value)

print("Change 6")
ctx.param.set(999)
ctx.compute()
print(ctx.mymacro.exception)
try:
    print(ctx.mymacro.ctx)
except AttributeError:
    print("ctx.mymacro.ctx is undefined")
else:
    print(ctx.mymacro.ctx.a.value)
    print(ctx.mymacro.ctx.b.value)
    print(ctx.mymacro.ctx.hasattr("d"))
    if ctx.mymacro.ctx.hasattr("d"):
        print(ctx.mymacro.ctx.d.value)
    print(ctx.mymacro.ctx.result.value)

print("STOP")

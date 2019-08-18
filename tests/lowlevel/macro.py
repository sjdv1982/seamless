import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, macro

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
        ctx.a.connect(ctx.tf.a)
        ctx.b.connect(ctx.tf.b)
        ctx.code = cell("transformer").set("print('TRANSFORM'); import time; time.sleep(2); c = a + b")
        ctx.code.connect(ctx.tf.code)
        ctx.tf.c.connect(ctx.result)
        assert param != 999   # on purpose
        if param > 1:
            ctx.d = cell().set(42)
            raise Exception("on purpose") #causes the macro reconstruction to fail
        pass # For some reason, comments at the end are not captured with inspect.get_source?

    ctx.mymacro_code = cell("macro").set(macro_code)
    ctx.mymacro_code.connect(ctx.mymacro.code)

    ctx.mount("/tmp/mount-test", persistent=False)


print("START")
ctx.equilibrate(1)
###ctx.equilibrate()
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(hasattr(ctx.mymacro.ctx, "d"))
print(ctx.mymacro.ctx.result.value) #None instead of 3002, unless you enable ctx.equilibrate() above

def mount_check():
    from seamless.core.mount import mountmanager #singleton
    paths = mountmanager.paths[ctx._root()]
    for c in (ctx.mymacro_code, ctx.param, ctx.mymacro.ctx.a, ctx.mymacro.ctx.b, ctx.mymacro.ctx.code):
        path = c._mount["path"]
        assert c in mountmanager.mounts, c
        assert path in paths, (c, path)
        assert mountmanager.mounts[c].path == path, (c, path, mountmanager.mounts[c].path)

mount_check()

print("Change 1")
ctx.param.set(2)
ctx.equilibrate()
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
    mount_check()

print("Change 2")
ctx.mymacro_code.set(
    ctx.mymacro_code.value + "   "
)
ctx.equilibrate() # Macro execution, because macros are not cached. But no transformation

try:
    ctx.mymacro.ctx
except AttributeError:
    pass
else:
    mount_check()

print("Change 3")
ctx.mymacro_code.set(
    ctx.mymacro_code.value.replace("#raise Exception", "raise Exception")
)
ctx.equilibrate()

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
    mount_check()

print("Change 4")
ctx.mymacro_code.set(
    ctx.mymacro_code.value.replace("raise Exception", "#raise Exception")
)
ctx.equilibrate()
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(ctx.mymacro.ctx.hasattr("d"))
if ctx.mymacro.ctx.hasattr("d"):
    print(ctx.mymacro.ctx.d.value)
print(ctx.mymacro.ctx.result.value)

print("Change 5")
ctx.param.set(0)
ctx.equilibrate()
print(ctx.mymacro.ctx.a.value)
print(ctx.mymacro.ctx.b.value)
print(ctx.mymacro.ctx.hasattr("d"))
if ctx.mymacro.ctx.hasattr("d"):
    print(ctx.mymacro.ctx.d.value)
print(ctx.mymacro.ctx.result.value)

mount_check()

print("Change 6")
ctx.param.set(999)
ctx.equilibrate()
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

    mount_check()

print("STOP")

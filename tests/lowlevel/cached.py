import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, macro

def run(a,b):
    print("RUN")
    """
    import time
    for n in range(10):
        print(n)
        time.sleep(1)
    print(n)
    """
    return a + b

def build(ctx, param, run):
    print("BUILD")
    tf = transformer(
    {
        "a": "input",
        "b": "input",
        "c": "output",
    })
    if param.startswith("PARAM"):
        ctx.tf_alt1 = tf
    else:
        ctx.tf_alt2 = tf
    ctx.tf = link(tf)

    ctx.run = pytransformercell().set(run)
    ctx.run.connect(tf.code)
    ctx.a = link(tf.a).export()
    ctx.b = link(tf.b).export()
    ctx.c = link(tf.c).export()
    ctx.param = cell("json").set(param)

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.macro = macro({
        "param":"copy",
        "run": ("copy", "text"),
    })
    ctx.macro_code = pytransformercell().set(build)
    ctx.macro_code.connect(ctx.macro.code)
    ctx.run = pytransformercell().set(run)
    ctx.run.connect(ctx.macro.run)
    ctx.param = cell("json").set("PARAM")
    ctx.param.connect(ctx.macro.param)
    ctx.a = cell("json").set(1)
    ctx.b = cell("json").set(2)
    ctx.c = cell()
    ctx.a.connect(ctx.macro.ctx.a)
    ctx.b.connect(ctx.macro.ctx.b)
    ctx.macro.ctx.c.connect(ctx.c)


ctx.equilibrate(0.5)
print(ctx.c.value)
print(ctx.macro.ctx.tf.status())
print()
print("CHANGE 1")
ctx.param.set("PARAM2")
ctx.equilibrate()
print(ctx.c.value)
print(ctx.macro.ctx.tf.status())
print("CHANGE 2")
ctx.param.set("x")
ctx.equilibrate()
print(ctx.c.value)
print(ctx.macro.ctx.tf.status())

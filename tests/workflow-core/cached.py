import seamless
seamless.delegate(False)

from seamless.workflow.core import macro_mode_on
from seamless.workflow.core import context, cell, transformer, macro

def run(a,b):
    print("RUN")
    import time
    for n in range(3):
        print("Running", n+1)
        time.sleep(1)
    return a + b

def build(ctx, param, run):
    print("BUILD")
    tf_params = {
        "a": "input",
        "b": "input",
        "c": "output",
    }
    ctx.tf1 = transformer(tf_params)
    ctx.tf1._debug = {
        "direct_print" : True
    }
    ctx.tf2 = transformer(tf_params)
    ctx.tf2._debug = {
        "direct_print" : True
    }
    tf = ctx.tf2 if param == "PARAM" else ctx.tf1

    ctx.run = cell("transformer").set(run)
    ctx.run.connect(tf.code)
    ctx.a = cell()
    ctx.b = cell()
    ctx.a.connect(tf.a)
    ctx.b.connect(tf.b)
    ctx.c = cell()
    tf.c.connect(ctx.c)
    ctx.param = cell().set(param)

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.macro = macro({
        "param": "plain",
        "run": "text",
    })
    ctx.macro_code = cell("macro").set(build)
    ctx.macro_code.connect(ctx.macro.code)
    ctx.run = cell("transformer").set(run)
    ctx.run.connect(ctx.macro.run)
    ctx.param = cell().set("PARAM")
    ctx.param.connect(ctx.macro.param)
    ctx.a = cell().set(1)
    ctx.b = cell().set(2)
    ctx.c = cell()
    ctx.a.connect(ctx.macro.ctx.a)
    ctx.b.connect(ctx.macro.ctx.b)
    ctx.macro.ctx.c.connect(ctx.c)

ctx.compute()
print(ctx.c.value)
print(ctx.macro.ctx.tf1.status)
print(ctx.macro.ctx.tf2.status)
print()

print("CHANGE 1")
ctx.param.set("PARAM2")
ctx.compute()
print(ctx.c.value)
print(ctx.macro.ctx.tf1.status)
print(ctx.macro.ctx.tf2.status)

print("CHANGE 2")
ctx.param.set("x")
ctx.compute()
print(ctx.c.value)
print(ctx.macro.ctx.tf1.status)
print(ctx.macro.ctx.tf2.status)

import seamless

seamless.delegate(False)

from seamless.workflow.highlevel import Context, Macro

ctx = Context()
m = ctx.m = Macro()
ctx.a = 10
m.a = ctx.a
m.b = 20
m.pins.x = {"io": "input", "celltype": "int"}
m.pins.y = {"io": "output", "celltype": "int"}


def run_macro(ctx, a, b):
    pins = {
        "a": "input",
        "b": "input",
        "x": "input",
        "y": "output",
    }
    ctx.tf = transformer(pins)
    ctx.tf.a.cell().set(a)
    ctx.tf.b.cell().set(b)
    ctx.x = cell("int")
    ctx.x.connect(ctx.tf.x)
    ctx.tf.code.cell().set("y = a * b + x")
    ctx.y = cell("int")
    ctx.tf.y.connect(ctx.y)


m.code = run_macro
ctx.compute()
print(m.status, m.exception)
print(ctx.m.ctx.status)
print(ctx.m.ctx.x.status)
print(ctx.m.ctx.x.value)
print(ctx.m.ctx.tf.status)
print(ctx.m.ctx.y.status, ctx.m.ctx.y.value)
print()

ctx.x = 2
m.x = ctx.x
ctx.y = m.y
ctx.compute()
print(m.status, m.exception)
print(ctx.m.ctx.status)
print(ctx.m.ctx.x.status)
print(ctx.m.ctx.x.value)
print(ctx.m.ctx.tf.status)
print(ctx.m.ctx.y.status, ctx.m.ctx.y.value)
print(ctx.y.status, ctx.y.value)
print()

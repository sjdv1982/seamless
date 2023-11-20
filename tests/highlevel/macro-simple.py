import seamless
seamless.delegate(False)

from seamless.highlevel import Context, Macro
ctx = Context()
m = ctx.m = Macro()
ctx.a = 10
m.a = ctx.a
m.b = 20
def run_macro(ctx, a, b):
    pins = {
        "a": "input", 
        "b": "input",
        "c": "output",
    }
    ctx.tf = transformer(pins)
    ctx.tf.a.cell().set(a)
    ctx.tf.b.cell().set(b)
    ctx.tf.code.cell().set("c = a * b")
    ctx.c = cell()
    ctx.tf.c.connect(ctx.c)
    return
m.code = run_macro
ctx.compute()
print(m.status, m.exception)
print(ctx.m.ctx.c.value)
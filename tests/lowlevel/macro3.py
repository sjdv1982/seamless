import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, \
  macro, link, path

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.mount("/tmp/mount-test")
    ctx.param = cell("plain").set(0)

    ctx.macro = macro({
        "param": "plain",
    })

    ctx.param.connect(ctx.macro.param)
    ctx.macro_code = cell("macro").set("""
ctx.sub = context()
ctx.a = cell("plain").set(1000 + param)
ctx.b = cell("plain").set(2000 + param)
ctx.result = cell("plain")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.a.connect(ctx.tf.a)
ctx.b.connect(ctx.tf.b)
ctx.code = cell("transformer").set("c = a + b")
ctx.code.connect(ctx.tf.code)
ctx.tf.c.connect(ctx.result)
assert param != 999   # on purpose
if param > 1:
    ctx.d = cell("plain").set(4200+param)
    ctx.tf2 = transformer({
        "e": "input",
        "e2": "output"
    })
    ctx.tf2.code.cell().set("e2 = 10 * e")
    ctx.tf2e = cell("plain")
    ctx.tf2e.connect(ctx.tf2.e)
    ctx.tf2e2 = cell("plain")
    ctx.tf2.e2.connect(ctx.tf2e2)

    #raise Exception("on purpose") #causes the macro reconstruction to fail; comment it out to make it succeed
ctx.x0 = cell("text").set("x" + str(param))
ctx.x = cell("text")
ctx.x_link = link(ctx.x)
ctx.y = cell("text").set("y" + str(param))
ctx.z = cell("text")
ctx.q = cell("text").set("q" + str(param))
ctx.qq = cell("text")
ctx.q_link = link(ctx.q)
ctx.r = cell("text").set("r" + str(param))
ctx.r_link = link(ctx.r)
ctx.rr = cell("text")
ctx.rr_link = link(ctx.rr)
""")
    ctx.macro_code.connect(ctx.macro.code)
    ctx.tfx = transformer({
        "x0": "input",
        "x": "output"
    })
    ctx.tfx.code.cell().set("x = x0 + '!'")
    ctx.tfx_x0 = cell("text")
    ctx.tfx_x0.connect(ctx.tfx.x0)
    ctx.macro.ctx.x0.connect(ctx.tfx_x0)
    ctx.x = cell("text")
    ctx.tfxx = cell("text")
    ctx.tfx.x.connect(ctx.tfxx)
    ctx.tfxx.connect(ctx.macro.ctx.x_link)
    ctx.tfx.x.connect(ctx.x)
    ctx.y = cell("text")
    ctx.macro.ctx.y.connect(ctx.y)
    ctx.e = cell("plain")
    ctx.e2 = cell("plain")
    p_d = path(ctx.macro.ctx).d
    p_d.connect(ctx.e)
    p_tf2e = path(ctx.macro.ctx).tf2e
    p_tf2e2 = path(ctx.macro.ctx).tf2e2
    ctx.e.connect(p_tf2e)
    p_tf2e2.connect(ctx.e2)
    ctx.z = cell("text").set("z")
    ctx.z_link = link(ctx.z)
    ctx.z_link.connect(ctx.macro.ctx.z)
    ctx.q = cell("text")
    ctx.macro.ctx.q_link.connect(ctx.q)
    ctx.subq = cell("text")
    ctx.macro.ctx.q.connect(ctx.subq)
    ctx.subq.connect(ctx.macro.ctx.qq)
    ctx.r = cell("text")
    ctx.r_link = link(ctx.r)
    ctx.macro.ctx.r_link.connect(ctx.r_link)
    ctx.r.connect(ctx.macro.ctx.rr_link)

def report():
    d = "<non-existent>"
    if ctx.macro.ctx.hasattr("d"):
        d = ctx.macro.ctx.d.value
    print("%-20s" % "d", d)
    print("%-20s" % "e", ctx.e.value)
    print("%-20s" % "e2", ctx.e2.value)
    print("%-20s" % "macro x0", ctx.macro.ctx.x0.value)
    print("%-20s" % "macro x", ctx.macro.ctx.x.value)
    print("%-20s" % "x", ctx.x.value)
    print("%-20s" % "macro y", ctx.macro.ctx.y.value)
    print("%-20s" % "y", ctx.y.value)
    print("%-20s" % "macro z", ctx.macro.ctx.z.value)
    print("%-20s" % "q", ctx.q.value)
    print("%-20s" % "macro q", ctx.macro.ctx.q.value)
    print("%-20s" % "macro q_link",ctx.macro.ctx.q_link.value)
    print("%-20s" % "macro qq", ctx.macro.ctx.qq.value)
    print("%-20s" % "r", ctx.r.value)
    print("%-20s" % "macro rr", ctx.macro.ctx.rr.value)
    print()

print("START")
ctx.equilibrate()

print("""Initial param 0
Should be non-existent for .d
Should be None for .e, .e2
""")
report()
print(ctx.status)

print("Change to 2")
ctx.param.set(2)
ctx.equilibrate()
report()
print(ctx.status)
import sys; sys.exit()

print("""Change to 1
Should change to non-existent for .d
Should change to None for .e, .e2
""")
ctx.param.set(1)
ctx.equilibrate()
report()
print(ctx.status)

print("Change to 3")
ctx.param.set(3)
ctx.equilibrate()
report()
print(ctx.status)

print("Change to 4")
ctx.param.set(4)
ctx.equilibrate()
report()
print(ctx.status)

print("STOP")
import sys; sys.exit()

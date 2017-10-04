ctx.period = cell("float").set(1.5)
import seamless
ctx.timer = seamless.lib.timer(ctx.period)
t = ctx.timer.trigger.cell()
t.connect(ctx.gen_uniforms.reset.cell())
t.connect(ctx.gen_vertexdata.reset.cell())

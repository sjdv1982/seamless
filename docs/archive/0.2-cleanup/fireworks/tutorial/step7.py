p.painted.connect(ctx.gen_uniforms.update.cell())

#  Repaint connection: has to be external, else it will be destroyed when ctx.program gets recreated
#  Does not seem to be necessary anymore??
#ctx.repaint = cell("signal")
#p.painted.connect(ctx.repaint)
#ctx.repaint.connect(p.update.cell())
#  /repaint connection

p.update.cell().touch()

import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell

ctx = Context()
ctx.a = Cell("text").set(10)
ctx.a.share()
ctx.sub = Context()
ctx.sub.b = ctx.a
# ctx.sub.b.celltype = "text"
ctx.sub.b.mimetype = "text"
ctx.sub.b.share()
ctx.compute()

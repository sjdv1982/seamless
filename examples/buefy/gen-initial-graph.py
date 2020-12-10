from seamless.highlevel import Context, Cell, Transformer

ctx = Context()

ctx.a = Cell("int").set(10)
ctx.a.share(readonly=False)
ctx.b = Cell("int").set(20)
ctx.b.share(readonly=False)
ctx.c = Cell("int").set(30).share()

ctx.tf = lambda a,b: a+b
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.c = ctx.tf

ctx.translate()
ctx.save_graph("initial-graph.seamless")
ctx.save_zip("initial-graph.zip")

# Vertexdata generator
ctx.N = cell("int").set(10000)
ctx.params_gen_vertexdata = cell(("cson", "seamless", "transformer_params"))
link(ctx.params_gen_vertexdata, ".", "params_gen_vertexdata.cson")
if not ctx.params_gen_vertexdata.value: ### kludge: to be fixed in seamless 0.2
    ctx.params_gen_vertexdata.set("{}")
ctx.gen_vertexdata = transformer(ctx.params_gen_vertexdata)
link(ctx.gen_vertexdata.code.cell(), ".", "cell-gen-vertexdata.py")

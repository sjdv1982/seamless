ctx.silk_vertexdata = cell(("text", "code", "silk"))
link(ctx.silk_vertexdata, ".", "vertexdata.silk")
if not ctx.silk_vertexdata.value: ### kludge: to be fixed in seamless 0.2
    ctx.silk_vertexdata.set("")
ctx.registrar.silk.register(ctx.silk_vertexdata)

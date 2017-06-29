del(ctx.attrib)
ctx.attrib2.connect(ctx.plotly.attrib)

del ctx.data
ctx.data2.connect(ctx.plotly.data)

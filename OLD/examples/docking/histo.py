from seamless import macro
@macro("str")
def histo(ctx, title):
    from seamless import export, cell
    from seamless.core.worker import ExportedInputPin, ExportedOutputPin
    from seamless.lib.plotly import plotly
    from seamless.lib import browse
    ctx.plotly = plotly(mode="nx")
    ctx.layout0 = cell("cson")
    ctx.layout0.connect(ctx.plotly.layout)
    ctx.attrib0 = cell("cson")
    ctx.attrib0.connect(ctx.plotly.attrib)
    ctx.attrib0.set("""[{
      type: 'histogram',
      histnorm: 'probability'
    	marker: {
        color: 'rgba(100,250,100,0.7)',
    	}
    }]""")
    ctx.layout0.set({})
    ctx.data = ExportedInputPin(ctx.plotly.data)
    ctx.attrib = ExportedInputPin(ctx.attrib0)
    ctx.layout = ExportedInputPin(ctx.layout0)
    ctx.html = ExportedOutputPin(ctx.plotly.html)
    browse(ctx.html.cell(), title)

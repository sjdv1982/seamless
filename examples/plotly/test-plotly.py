import seamless
from seamless import context, cell
from seamless.lib import link, browse
from seamless.lib.plotly import plotly

ctx = context()
ctx.plotly = plotly()

ctx.data = cell("text")
ctx.link_data = link(ctx.data, ".", "data.csv")
ctx.layout = cell("cson")
ctx.link_layout = link(ctx.layout, ".", "layout.cson")
ctx.attrib = cell("cson")
ctx.link_attrib = link(ctx.attrib, ".", "attrib.cson")

ctx.data.connect(ctx.plotly.data)
ctx.attrib.connect(ctx.plotly.attrib)
ctx.layout.connect(ctx.plotly.layout)

ctx.html = cell(("text", "html")).set("Hello world")
#ctx.plotly.html.connect(ctx.html)
ctx.browser_static = browse(ctx.html)

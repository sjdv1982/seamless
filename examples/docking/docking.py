from seamless import context, cell
from seamless.lib import edit, display, link, browse
from seamless.slash import slash0

ctx = context()
ctx.attract = cell(("text", "code", "slash-0"))
ctx.link_attract = link(ctx.attract, ".", "attract.slash")
ctx.equilibrate()
ctx.slash = slash0(ctx.attract)
ctx.pdbA = cell("text")
ctx.pdbB = cell("text")
ctx.link_pdbA = link(ctx.pdbA, ".", "1AVXA.pdb")
ctx.link_pdbB = link(ctx.pdbB, ".", "1AVXB.pdb")
ctx.pdbA.connect(ctx.slash.pdbA)
ctx.pdbB.connect(ctx.slash.pdbB)
ctx.energies = cell("text")
ctx.slash.energies.connect(ctx.energies)
display(ctx.energies, "Energies")

from seamless.lib.plotly import plotly
ctx.plotly = plotly(dynamic_html=True,mode="nx")
ctx.energies.connect(ctx.plotly.data)

ctx.plotly_layout = cell("cson")
ctx.link_plotly_layout = link(ctx.plotly_layout, ".", "plotly_layout.cson")
ctx.plotly_attrib = cell("cson")
ctx.link_plotly_attrib = link(ctx.plotly_attrib, ".", "plotly_attrib.cson")
ctx.plotly_layout.connect(ctx.plotly.layout)
ctx.plotly_attrib.connect(ctx.plotly.attrib)

ctx.html = cell(("text", "html"))
ctx.plotly.html.connect(ctx.html)
ctx.browser_static = browse(ctx.html, "Plotly, static HTML")

ctx.dynamic_html = cell(("text", "html"))
ctx.plotly.dynamic_html.connect(ctx.dynamic_html)
ctx.browser_dynamic = browse(ctx.dynamic_html, "Plotly, dynamic HTML")

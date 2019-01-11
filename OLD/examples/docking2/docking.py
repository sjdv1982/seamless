import os, sys
get_ipython().system('./load-test.sh')

#Stage 1: display test dataset
from seamless import context, cell, reactor, transformer, export
from seamless.lib import link, browse
from seamless.lib.plotly import plotly
ctx = context()
ctx.plotly = plotly(dynamic_html=True)
ctx.plotly.values.width.set(800)
ctx.plotly.values.height.set(600)
c = export(ctx.plotly.data, "cson").fromfile("data.cson")
link(c)
c = export(ctx.plotly.attrib, "cson").fromfile("attrib.cson")
link(c)
c = export(ctx.plotly.layout, "cson").fromfile("layout.cson")
link(c)
c = export(ctx.plotly.html)
link(c, ".", "plotly.html")
browse(c, "Docking clusters")
c = export(ctx.plotly.dynamic_html)
link(c, ".", "plotly-dynamic.html")
browse(c, "Docking clusters (dynamic)")

#Stage 2: load real dataset
get_ipython().system('./load-real.sh')

#Stage 2a: perform (bound) docking,
# (re)generating real dataset in cells data2, attrib2
import numpy as np
ctx.attract = cell(("text", "code", "slash-0"))
from seamless.slash import slash0
ctx.slash = slash0(ctx.attract)
ctx.attract.fromfile("attract.slash")
link(ctx.attract)
export(ctx.slash.energies)
export(ctx.slash.ntop, "int").set(100)
export(ctx.slash.clust_cutoff, "float").set(10)
edit(ctx.ntop, "Top structures")
edit(ctx.clust_cutoff, "Clustering cutoff")
display(ctx.energies, "Energies")
export(ctx.slash.irmsds)
display(ctx.irmsds, "i-RMSD")
export(ctx.slash.clusters)
display(ctx.clusters, "clusters")
ctx.colors = cell("text").fromfile("colors.txt")
link(ctx.colors)
ctx.gen_data = transformer({
"colors": {"pin": "input", "dtype":"text"},
"irmsds": {"pin": "input", "dtype":"text"},
"energies": {"pin": "input", "dtype":"text"},
"clusters": {"pin": "input", "dtype":"text"},
"data": {"pin": "output", "dtype": "json"},
})
ctx.gen_data.code.cell().fromfile("cell-gen-data.py")
link(ctx.gen_data.code.cell())
ctx.colors.connect(ctx.gen_data.colors)
ctx.clusters.connect(ctx.gen_data.clusters)
ctx.irmsds.connect(ctx.gen_data.irmsds)
ctx.energies.connect(ctx.gen_data.energies)
ctx.data2 = cell("json")
ctx.gen_data.data.connect(ctx.data2)
ctx.gen_attrib = transformer({
"colors": {"pin": "input", "dtype":"text"},
"clusters": {"pin": "input", "dtype":"text"},
"attrib": {"pin": "output", "dtype": "json"},
})
ctx.colors.connect(ctx.gen_attrib.colors)
ctx.clusters.connect(ctx.gen_attrib.clusters)
ctx.attrib2 = cell("json")
ctx.gen_attrib.attrib.connect(ctx.attrib2)
ctx.gen_attrib.code.cell().fromfile("cell-gen-attrib.py")
link(ctx.gen_attrib.code.cell())
export(ctx.slash.nstrucdone, "int")
display(ctx.nstrucdone, "#structures done")

#Reconnect attrib2 to ctx.plotly.attrib, data2 to ctx.plotly.data
get_ipython().magic('run -i reconnect.py')
ctx.equilibrate()
ctx.tofile("attract.seamless", backup=False)

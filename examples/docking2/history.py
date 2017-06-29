# IPython log file

import os
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
link(ctx.data2, ".", "data.json")
link(ctx.attrib2, ".", "attrib.json")
ctx.gen_attrib.attrib.connect(ctx.attrib2)
ctx.gen_attrib.code.cell().fromfile("cell-gen-attrib.py")
link(ctx.gen_attrib.code.cell())
export(ctx.slash.nstrucdone, "int")
display(ctx.nstrucdone, "#structures done")

#reconnect.py
"""
del(ctx.attrib)
ctx.attrib2.connect(ctx.plotly.attrib)

del ctx.data
ctx.data2.connect(ctx.plotly.data)
"""

#ctx.tofile("attract.seamless", backup=False)

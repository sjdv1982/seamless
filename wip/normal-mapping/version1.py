"""
import seamless
from seamless import context, cell, pythoncell, transformer, reactor, \
 macro, export
from seamless.lib import link, edit, display
from seamless.gui import shell
ctx = context()
"""

#ctx.display_numpy = ctx.fromfile("../display-numpy/display_numpy.seamless")
#KLUDGE
ctx = ctx.fromfile("../display-numpy/display_numpy.seamless")
ctx.rc_display_numpy = ctx.display_numpy
ctx.display_numpy = context()
ctx.display_numpy.array = ctx.array
ctx.display_numpy.title = ctx.title
#/KLUDGE

ctx.texture = cell("array")
ctx.texture.set_store("GLTex", 2)
ctx.texture.connect(ctx.display_numpy.array)
import numpy as np
print("START")
ctx.gen_texture = transformer({"texture": {"pin": "output", "dtype": "array"}})
ctx.gen_texture.texture.connect(ctx.texture)
link(ctx.gen_texture.code.cell(), ".", "cell-gen-texture.py")

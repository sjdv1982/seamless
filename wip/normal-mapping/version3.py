"""
import seamless
from seamless import context, cell, pythoncell, transformer, reactor, \
 macro, export
from seamless.lib import link, edit, display
from seamless.gui import shell
ctx = context()
"""


import seamless
from seamless import context, cell, transformer, reactor
from seamless.lib import edit, display, link

ctx = seamless.fromfile("test-sphere3.seamless")
#KLUDGE; although file dominant, differences do not trigger a macro update... need to make a new test-sphere.seamless

del ctx.subdivisions
del ctx.edit.subdivisions
del ctx.minimizations
del ctx.edit.minimizations
del ctx.gen_sphere
del ctx.params.gen_sphere
del ctx.links.params_gen_sphere
del ctx.links.code_gen_sphere


ctx.texture_coords = cell("array").set_store("GL")
ctx.triangle_texture_coords = cell("array").set_store("GL")


#for now, load-ply must be a reactor, because it has multiple outputs
#TODO: make it a transformer in a future version of seamless
c = ctx.params.load_ply = cell(("cson", "seamless", "reactor_params"))
ctx.links.params_load_ply = link(c, ".", "params-load-ply.cson")
rc = ctx.load_ply = reactor(c)
c = ctx.code.load_ply = cell(("text", "code", "python"))
ctx.links.code_load_ply = link(c, ".", "cell-load-ply2.py")
rc.code_start.cell().set("")
c.connect(rc.code_update)
rc.code_stop.cell().set("")

ctx.load_ply.coordinates.connect(ctx.coordinates_prescale)
ctx.load_ply.normals.connect(ctx.normals)
ctx.load_ply.edges.connect(ctx.edges)
ctx.load_ply.triangle_indices.connect(ctx.triangle_indices)
ctx.load_ply.triangle_coordinates.connect(ctx.triangle_coordinates_prescale)
ctx.load_ply.triangle_normals.connect(ctx.triangle_normals)
ctx.load_ply.texture_coords.connect(ctx.texture_coords)
ctx.load_ply.triangle_texture_coords.connect(ctx.triangle_texture_coords)
ctx.filename = cell("str")
ctx.filename.connect(ctx.load_ply.filename)

#ctx.filename.set("suzanne.ply")
#ctx.scale.set(3.0)

ctx.filename.set("lion-statue.ply")
ctx.scale.set(1.0)

#ctx.filename.set("metallic-lucy-statue-stanford-scan.ply.zip")
#ctx.scale.set(5.0)

print("In the 3D window, press key 1-4 to change the states")

""" #even the kludge does not work... troubles when updating macro
#ctx.display_numpy = ctx.fromfile("../display-numpy/display_numpy.seamless")
#KLUDGE
ctx = ctx.fromfile("../display-numpy/display_numpy.seamless")
ctx.rc_display_numpy = ctx.display_numpy
ctx.display_numpy = context()
ctx.display_numpy.array = ctx.array
ctx.display_numpy.title = ctx.title
#/KLUDGE
seamless.core.context.set_active_context(ctx) #does not help
"""

ctx_bak = ctx
ctx.display_numpy = context()
ctx = ctx.display_numpy
###
ctx.array = cell("array")
ctx.title = cell("str").set("Numpy array")
ctx.aspect_layout = pythoncell().fromfile("AspectLayout.py")
ctx.registrar.python.register(ctx.aspect_layout)
ctx.display_numpy = reactor({
    "array": {"pin": "input", "dtype": "array"},
    "title": {"pin": "input", "dtype": "str"},
})
ctx.registrar.python.connect("AspectLayout", ctx.display_numpy)
ctx.array.connect(ctx.display_numpy.array)
ctx.title.connect(ctx.display_numpy.title)

ctx.display_numpy.code_update.set("update()")
ctx.display_numpy.code_stop.set("destroy()")
ctx.code = pythoncell()
ctx.code.connect(ctx.display_numpy.code_start)
ctx.code.fromfile("cell-display-numpy.py")
###
ctx = ctx_bak


ctx.texture = cell("array")
ctx.texture.set_store("GLTex", 2)
ctx.texture.connect(ctx.display_numpy.array)
import numpy as np
print("START")
ctx.equilibrate()
ctx.gen_texture = transformer({
    "filename": {"pin": "input", "dtype": "str"},
    "texture": {"pin": "output", "dtype": "array"}
})
ctx.gen_texture.texture.connect(ctx.texture)
link(ctx.gen_texture.code.cell(), ".", "cell-gen-texture.py")
ctx.equilibrate()

ctx.texture_coords.connect(ctx.tri_program.array_texture_coords)
ctx.triangle_texture_coords.connect(ctx.ftri_program.array_texture_coords)
ctx.texture.connect(ctx.tri_program.array_s_texture)
ctx.texture.connect(ctx.ftri_program.array_s_texture)

import os
ctx.texture_filename = cell(str).set("textures/Bricks.png")
ctx.texture_filename.connect(ctx.gen_texture.filename)

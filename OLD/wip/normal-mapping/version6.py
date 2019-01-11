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

ctx = seamless.fromfile("test-sphere4.seamless")
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

###
first = True
def load_display_numpy():
    global first
    ctx.array = cell("array")
    ctx.title = cell("str").set("Numpy array")
    ctx.aspect_layout = pythoncell().fromfile("AspectLayout.py")
    if first:
        ctx.registrar.python.register(ctx.aspect_layout) #TODO: should be harmless to register same item twice
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
    first = False

ctx_bak = ctx
ctx.display_numpy = context()
ctx = ctx.display_numpy
load_display_numpy()
ctx = ctx_bak

ctx_bak = ctx
ctx.display_numpy2 = context()
ctx = ctx.display_numpy2
load_display_numpy()
ctx = ctx_bak

###


ctx.texture = cell("array")
ctx.texture.set_store("GLTex", 2)
ctx.display_numpy.title.set("Texture")
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

ctx.texture_filename = cell(str).set("textures/Bricks.png")
ctx.texture_filename.connect(ctx.gen_texture.filename)

ctx.normal_map = cell("array").set_store("GLTex", 2)
ctx.gen_normal_map = transformer({
    "normal_map": {"pin": "output", "dtype": "array"}
})
ctx.gen_normal_map.normal_map.connect(ctx.normal_map)
link(ctx.gen_normal_map.code.cell(), ".", "cell-gen-normal-map.py")

ctx.display_numpy2.title.set("Normal map")
ctx.normal_map.connect(ctx.display_numpy2.array)

ctx.equilibrate()

ctx.texture_coords.connect(ctx.tri_program.array_texture_coords)
ctx.triangle_texture_coords.connect(ctx.ftri_program.array_texture_coords)
#ctx.texture.connect(ctx.tri_program.array_s_texture)
#ctx.texture.connect(ctx.ftri_program.array_s_texture)
ctx.normal_map.connect(ctx.tri_program.array_s_texture)
ctx.normal_map.connect(ctx.ftri_program.array_s_texture)

ctx.tangents = cell("array").set_store("GL")
ctx.gen_tangents = transformer({
    "positions": {"pin": "input", "dtype": "array"},
    "uv": {"pin": "input", "dtype": "array"},
    "normals": {"pin": "input", "dtype": "array"},
    "indices": {"pin": "input", "dtype": "array"},
    "tangents": {"pin": "output", "dtype": "array"},
})
ctx.coordinates.connect(ctx.gen_tangents.positions)
ctx.normals.connect(ctx.gen_tangents.normals)
ctx.texture_coords.connect(ctx.gen_tangents.uv)
ctx.triangle_indices.connect(ctx.gen_tangents.indices)
ctx.gen_tangents.tangents.connect(ctx.tangents)
c = ctx.code.gen_tangents = pythoncell()
c.connect(ctx.gen_tangents.code )
ctx.links.code_gen_tangents = link(c, ".", "cell-gen-tangents.py")

ctx.lines = cell("array").set_store("GL")
ctx.params.gen_lines = cell("cson")
ctx.links.gen_lines = link(ctx.params.gen_lines, ".", "gen-lines.cson")
ctx.gen_lines = transformer(ctx.params.gen_lines)
ctx.edges.connect(ctx.gen_lines.edges)
ctx.coordinates.connect(ctx.gen_lines.coordinates)
ctx.normals.connect(ctx.gen_lines.normals)
ctx.tangents.connect(ctx.gen_lines.tangents)
ctx.gen_lines.lines.connect(ctx.lines)
c = ctx.code.gen_lines = pythoncell()
c.connect(ctx.gen_lines.code)
ctx.links.code_gen_lines = link(c, ".", "cell-gen-lines.py")

ctx.lines.connect(ctx.lines_program.array_lines)
ctx.selector.code_start.cell().set("state = 1")

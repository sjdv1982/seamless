import seamless
from seamless import context, cell, transformer, reactor
from seamless.lib import edit, display, link

ctx = seamless.fromfile("test-sphere.seamless")

del ctx.subdivisions
del ctx.edit.subdivisions
del ctx.minimizations
del ctx.edit.minimizations
del ctx.gen_sphere
del ctx.params.gen_sphere
del ctx.links.params_gen_sphere
del ctx.links.code_gen_sphere

#for now, load-ply must be a reactor, because it has multiple outputs
#TODO: make it a transformer in a future version of seamless
c = ctx.params.load_ply = cell(("cson", "seamless", "reactor_params"))
ctx.links.params_load_ply = link(c, ".", "params-load-ply.cson")
rc = ctx.load_ply = reactor(c)
c = ctx.code.load_ply = cell(("text", "code", "python"))
ctx.links.code_load_ply = link(c, ".", "cell-load-ply.py")
rc.code_start.cell().set("")
c.connect(rc.code_update)
rc.code_stop.cell().set("")

ctx.load_ply.coordinates.connect(ctx.coordinates_prescale)
ctx.load_ply.normals.connect(ctx.normals)
ctx.load_ply.edges.connect(ctx.edges)
ctx.load_ply.triangle_indices.connect(ctx.triangle_indices)
ctx.load_ply.triangle_coordinates.connect(ctx.triangle_coordinates_prescale)
ctx.load_ply.triangle_normals.connect(ctx.triangle_normals)
ctx.filename = cell("str")
ctx.filename.connect(ctx.load_ply.filename)

#ctx.filename.set("suzanne.ply")
#ctx.scale.set(3.0)

ctx.filename.set("lion-statue.ply")
ctx.scale.set(1.0)

#ctx.filename.set("metallic-lucy-statue-stanford-scan.ply.zip")
#ctx.scale.set(5.0)

print("In the 3D window, press key 1-4 to change the states")

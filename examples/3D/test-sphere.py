from seamless import context, cell, transformer, reactor
from seamless.lib import edit, display, link
from seamless.lib.gui.gl import glprogram, glwindow

import numpy as np
from scipy.spatial.distance import cdist

ctx = context()
ctx.params = context()
ctx.links = context()
ctx.code = context()

#for now, gen_sphere must be a reactor, because it has multiple outputs
#TODO: make it a transformer in a future version of seamless
#c = ctx.params.gen_sphere = cell(("cson", "seamless", "reactor_params"))
c = ctx.params.gen_sphere = cell("text")
ctx.links.params_gen_sphere = link(c, ".", "params-gen-sphere.cson")
rc = ctx.gen_sphere = reactor(c)
c = ctx.code.gen_sphere = cell(("text", "code", "python"))
ctx.links.code_gen_sphere = link(c, ".", "cell-gen-sphere.py")
rc.code_start.cell().set("")
c.connect(rc.code_update)
rc.code_stop.cell().set("")

do_scale_params = {
    "input":{"pin": "input", "dtype": "array"},
    "scale":{"pin": "input", "dtype": "float"},
    "output":{"pin": "output", "dtype": "array"}
}
ctx.subdivisions = cell("int").set(3)
ctx.minimizations = cell("int").set(20)
ctx.scale = cell("float").set(3.5)
ctx.coordinates = cell("array").set_store("GL")
ctx.normals = cell("array").set_store("GL")
ctx.edges = cell("array").set_store("GL")
ctx.triangle_indices = cell("array").set_store("GL")
ctx.triangle_normals = cell("array").set_store("GL")
ctx.triangle_coordinates = cell("array").set_store("GL")

ctx.coordinates_prescale = cell("array")
ctx.do_scale = transformer(do_scale_params)
ctx.scale.connect(ctx.do_scale.scale)
ctx.coordinates_prescale.connect(ctx.do_scale.input)
ctx.do_scale.output.connect(ctx.coordinates)
ctx.do_scale.code.set("return scale * input")

ctx.triangle_coordinates_prescale = cell("array")
ctx.do_scale2 = transformer(do_scale_params)
ctx.scale.connect(ctx.do_scale2.scale)
ctx.triangle_coordinates_prescale.connect(ctx.do_scale2.input)
ctx.do_scale2.output.connect(ctx.triangle_coordinates)
ctx.do_scale2.code.set("return scale * input")

ctx.subdivisions.connect(ctx.gen_sphere.subdivisions)
ctx.minimizations.connect(ctx.gen_sphere.minimizations)
ctx.gen_sphere.coordinates.connect(ctx.coordinates_prescale)
ctx.gen_sphere.normals.connect(ctx.normals)
ctx.gen_sphere.edges.connect(ctx.edges)
ctx.gen_sphere.triangle_indices.connect(ctx.triangle_indices)
ctx.gen_sphere.triangle_coordinates.connect(ctx.triangle_coordinates_prescale)
ctx.gen_sphere.triangle_normals.connect(ctx.triangle_normals)

ctx.params.gen_uniforms = cell("json").set({
    "input": {"pin": "input", "dtype": "json"},
    "output": {"pin": "output", "dtype": "json"},
})
ctx.window = glwindow("Seamless OpenGL 3D Example")


# Uniforms
ctx.gen_uniforms = transformer(ctx.params.gen_uniforms)
ctx.gen_uniforms.code.cell().set("""
result = {
    "u_modelview_matrix": input["modelview_matrix"],
    "u_projection_matrix": input["projection_matrix"],
    "u_normal_matrix": input["normal_matrix"],
    "u_mvp_matrix": input["mvp_matrix"],
}
return result
""")
identity = np.eye(4).tolist()
ctx.uniforms = cell("json")
ctx.window.camera.connect(ctx.uniforms)
ctx.uniforms.connect(ctx.gen_uniforms.input)

# Lines program
ctx.params.lines = cell("cson")
ctx.links.lines = link(ctx.params.lines, ".", "lines.cson")
ctx.lines_program = glprogram(ctx.params.lines, with_window=False)
ctx.window.init.cell().connect(ctx.lines_program.init)
#ctx.window.paint.cell().connect(ctx.lines_program.paint) # taken over by selector
ctx.lines_program.repaint.cell().connect(ctx.window.update)
ctx.coordinates.connect(ctx.lines_program.array_coordinates)
ctx.edges.connect(ctx.lines_program.array_edges)
ctx.gen_uniforms.output.cell().connect(ctx.lines_program.uniforms)

# Lines shaders
ctx.lines_vertexshader = cell(("text", "code", "vertexshader"))
ctx.lines_fragmentshader = cell(("text", "code", "fragmentshader"))
ctx.links.lines_vertexshader = link(ctx.lines_vertexshader, ".", "lines.vert")
ctx.links.lines_fragmentshader = link(ctx.lines_fragmentshader, ".", "lines.frag")
ctx.lines_vertexshader.connect(ctx.lines_program.vertex_shader)
ctx.lines_fragmentshader.connect(ctx.lines_program.fragment_shader)

# Triangle shaders
ctx.tri_vertexshader = cell(("text", "code", "vertexshader"))
ctx.tri_fragmentshader = cell(("text", "code", "fragmentshader"))
ctx.links.tri_vertexshader = link(ctx.tri_vertexshader, ".", "triangles.vert")
ctx.links.tri_fragmentshader = link(ctx.tri_fragmentshader, ".", "triangles.frag")

# Smooth triangles program
ctx.params.tri = cell("cson")
ctx.links.tri = link(ctx.params.tri, ".", "triangles-smooth.cson")
ctx.tri_program = glprogram(ctx.params.tri, with_window=False)
ctx.window.init.cell().connect(ctx.tri_program.init)
#ctx.window.paint.cell().connect(ctx.tri_program.paint) # taken over by selector
ctx.tri_program.repaint.cell().connect(ctx.window.update)
ctx.coordinates.connect(ctx.tri_program.array_coordinates)
ctx.normals.connect(ctx.tri_program.array_normals)
ctx.triangle_indices.connect(ctx.tri_program.array_indices)
ctx.gen_uniforms.output.cell().connect(ctx.tri_program.uniforms)
ctx.tri_vertexshader.connect(ctx.tri_program.vertex_shader)
ctx.tri_fragmentshader.connect(ctx.tri_program.fragment_shader)

# Flat triangles program
ctx.params.ftri = cell("cson")
ctx.links.ftri = link(ctx.params.ftri, ".", "triangles-flat.cson")
ctx.ftri_program = glprogram(ctx.params.ftri, with_window=False)
ctx.window.init.cell().connect(ctx.ftri_program.init)
#ctx.window.paint.cell().connect(ctx.ftri_program.paint) # taken over by selector
ctx.ftri_program.repaint.cell().connect(ctx.window.update)
ctx.triangle_coordinates.connect(ctx.ftri_program.array_coordinates)
ctx.triangle_normals.connect(ctx.ftri_program.array_normals)
ctx.gen_uniforms.output.cell().connect(ctx.ftri_program.uniforms)
ctx.tri_vertexshader.connect(ctx.ftri_program.vertex_shader)
ctx.tri_fragmentshader.connect(ctx.ftri_program.fragment_shader)

#Program selector
c = ctx.params.selector = cell(("cson", "seamless", "reactor_params"))
ctx.links.params_selector = link(c, ".", "params-selector.cson")
s = ctx.selector = reactor(c)
ctx.window.paint.cell().connect(s.paint)
s.paint_lines.cell().connect(ctx.lines_program.paint)
s.paint_triangles_smooth.cell().connect(ctx.tri_program.paint)
s.paint_triangles_flat.cell().connect(ctx.ftri_program.paint)
s.code_start.cell().set("state = 4")
s.code_stop.cell().set("")
c = ctx.code.selector = cell(("text", "code", "python"))
ctx.links.code_selector = link(c, ".", "cell-selector.py")
c.connect(s.code_update)
ctx.window.last_key.cell().connect(s.key)
s.repaint.cell().connect(ctx.window.update)
#kludge: must_be_defined does not work yet for input pins (TODO)
s.key.cell().set(" ")
s.key.cell().resource.save_policy = 4
#/kludge
#Kick-start the rendering
s.repaint.cell().set()

#Parameter editing
ctx.edit = context()
ctx.edit.scale = edit(ctx.scale, "Scale")
ctx.edit.subdivisions = edit(ctx.subdivisions, "Subdivisions")
ctx.edit.subdivisions.maximum.cell().set(7)
ctx.edit.minimizations = edit(ctx.minimizations, "Minimizations")
ctx.edit.minimizations.maximum.cell().set(100)

ctx.tofile("test-sphere.seamless", backup=False)
print("In the 3D window, press key 1-4 to change the states")

from seamless import context, cell, transformer, reactor
from seamless.lib import edit, display, link
from seamless.lib.gui.gl import glprogram, glwindow

import numpy as np

ctx = context()
ctx.params = context()
ctx.links = context()
ctx.code = context()

#for now, gen_sphere must be a reactor, because it has multiple outputs
#TODO: make it a transformer in a future version of seamless
c = ctx.params.gen_sphere = cell(("cson", "seamless", "reactor_params"))
ctx.links.params_gen_sphere = link(c, ".", "params-gen-sphere.cson")
rc = ctx.gen_sphere = reactor(c)
c = ctx.code.gen_sphere = cell(("text", "code", "python"))
ctx.links.code_gen_sphere = link(c, ".", "cell-gen-sphere.py")
rc.code_start.cell().set("")
c.connect(rc.code_update)
rc.code_stop.cell().set("")

ctx.subdivisions = cell("int").set(3)
ctx.minimizations = cell("int").set(20)
ctx.coordinates = cell("array").set_store("GL")
ctx.normals = cell("array").set_store("GL")
ctx.edges = cell("array").set_store("GL")
ctx.triangle_indices = cell("array").set_store("GL")
ctx.triangle_normals = cell("array").set_store("GL")
ctx.triangle_coordinates = cell("array").set_store("GL")

ctx.subdivisions.connect(ctx.gen_sphere.subdivisions)
ctx.minimizations.connect(ctx.gen_sphere.minimizations)
ctx.gen_sphere.coordinates.connect(ctx.coordinates)
ctx.gen_sphere.normals.connect(ctx.normals)
ctx.gen_sphere.edges.connect(ctx.edges)
ctx.gen_sphere.triangle_indices.connect(ctx.triangle_indices)
ctx.gen_sphere.triangle_coordinates.connect(ctx.triangle_coordinates)
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

# Atom shaders
ctx.atom_vertexshader = cell(("text", "code", "vertexshader"))
ctx.atom_fragmentshader = cell(("text", "code", "fragmentshader"))
ctx.links.atom_vertexshader = link(ctx.atom_vertexshader, ".", "atom.vert")
ctx.links.atom_fragmentshader = link(ctx.atom_fragmentshader, ".", "atom.frag")

# Atom program
ctx.params.atom = cell("cson")
ctx.links.atom = link(ctx.params.atom, ".", "atom.cson")
ctx.atom_program = glprogram(ctx.params.atom, with_window=False)
ctx.window.init.cell().connect(ctx.atom_program.init)
ctx.window.paint.cell().connect(ctx.atom_program.paint)
ctx.atom_program.repaint.cell().connect(ctx.window.update)
ctx.coordinates.connect(ctx.atom_program.array_coordinates)
ctx.normals.connect(ctx.atom_program.array_normals)
ctx.triangle_indices.connect(ctx.atom_program.array_indices)
ctx.gen_uniforms.output.cell().connect(ctx.atom_program.uniforms)
ctx.atom_vertexshader.connect(ctx.atom_program.vertex_shader)
ctx.atom_fragmentshader.connect(ctx.atom_program.fragment_shader)

ctx.atoms = cell("array").set_store("GL")
ctx.atoms.connect(ctx.atom_program.array_atoms)

# PDB loader
c = ctx.params.load_pdb = cell(("json", "seamless", "transformer_params"))
c.set({
    "filename": {"pin": "input", "dtype": "str"},
    "atoms": {"pin": "output", "dtype": "array"},
})
tf = ctx.load_pdb = transformer(c)
c = ctx.code.load_pdb = cell(("text", "code", "python"))
ctx.links.code_load_pdb = link(c, ".", "cell-load-pdb.py")
c.connect(tf.code)
ctx.filename = cell("str").set("1AVXA.pdb")
ctx.filename.connect(tf.filename)
tf.atoms.connect(ctx.atoms)

#Parameter editing
ctx.edit = context()
ctx.edit.subdivisions = edit(ctx.subdivisions, "Subdivisions")
ctx.edit.subdivisions.maximum.cell().set(7)
ctx.edit.minimizations = edit(ctx.minimizations, "Minimizations")
ctx.edit.minimizations.maximum.cell().set(100)

#ctx.tofile("test-atom.seamless", backup=False)

from seamless import cell, pythoncell, context, reactor, transformer
from seamless.silk import Silk
import seamless.lib
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display
from seamless.lib import link
from seamless.lib.gui.gl import glprogram

ctx = context()
file_dominant = False

# Vertexdata Silk model
ctx.silk_vertexdata = cell(("text", "code", "silk"))
ctx.link_silk_vertexdata = link(
    ctx.silk_vertexdata,
    ".", "vertexdata.silk",
    file_dominant=file_dominant
)
ctx.registrar.silk.register(ctx.silk_vertexdata)

# Shaders
ctx.vert_shader = cell(("text", "code", "vertexshader"))
ctx.frag_shader = cell(("text", "code", "fragmentshader"))
ctx.link_vert_shader = link(ctx.vert_shader, ".", "vert_shader.glsl",
    file_dominant=file_dominant)
ctx.link_frag_shader = link(ctx.frag_shader, ".", "frag_shader.glsl",
    file_dominant=file_dominant)

# Program template
ctx.program_template = cell("cson")
ctx.link_program_template = link(ctx.program_template,
    ".", "program_template.cson",
    file_dominant=file_dominant)

# Program and program generator
ctx.program = cell("json")
ctx.program.resource.save_policy = 4 #always save the program
ctx.gen_program = transformer({"program_template": {"pin": "input", "dtype": "json"},
                               "program": {"pin": "output", "dtype": "json"}})
ctx.registrar.silk.connect("VertexData", ctx.gen_program)
ctx.link_gen_program = link(ctx.gen_program.code.cell(),
    ".", "cell-gen-program.py",
    file_dominant=file_dominant)
ctx.program_template.connect(ctx.gen_program.program_template)
ctx.gen_program.program.connect(ctx.program)

#GL program
ctx.equilibrate() #ctx.program has to be generated first
p = ctx.glprogram = glprogram(ctx.program, window_title="Seamless fireworks demo")
ctx.frag_shader.connect(p.fragment_shader)
ctx.vert_shader.connect(p.vertex_shader)

# Vertexdata generator
ctx.N = cell("int").set(10000)
ctx.params_gen_vertexdata = cell(("json", "seamless", "transformer_params"))
ctx.link_params_gen_vertexdata = link(
    ctx.params_gen_vertexdata,
    ".", "params_gen_vertexdata.json",
    file_dominant=file_dominant)
ctx.equilibrate()
ctx.gen_vertexdata = transformer(ctx.params_gen_vertexdata)
ctx.N.connect(ctx.gen_vertexdata.N)
ctx.registrar.silk.connect("VertexData", ctx.gen_vertexdata)
ctx.registrar.silk.connect("VertexDataArray", ctx.gen_vertexdata)

ctx.vertexdata = cell("array")
ctx.vertexdata.set_store("GL") #OpenGL buffer store
ctx.link_gen_vertexdata = link(ctx.gen_vertexdata.code.cell(), ".",
  "cell-gen-vertexdata.py", file_dominant=file_dominant)
ctx.gen_vertexdata.output.connect(ctx.vertexdata)
ctx.vertexdata.connect(p.array_vertexdata)

# Texture generator
ctx.params_gen_texture = cell(("json", "seamless", "transformer_params"))
ctx.link_params_gen_texture = link(ctx.params_gen_texture,
    ".", "params_gen_texture.json", file_dominant=file_dominant)
ctx.texture = cell("array")
ctx.texture.set_store("GLTex", 2) #OpenGL texture store, 2D texture
ctx.equilibrate()
ctx.gen_texture = transformer(ctx.params_gen_texture)
ctx.link_gen_texture = link(ctx.gen_texture.code.cell(),
    ".", "cell-gen-texture.py", file_dominant=file_dominant)
ctx.tex_radius = ctx.gen_texture.radius.cell()
ctx.tex_radius.set(32)
ctx.tex_filename = ctx.gen_texture.filename.cell()
ctx.tex_filename.set("")
ctx.gen_texture.as_float.cell().set(True)
ctx.gen_texture.output.connect(ctx.texture)
ctx.texture.connect(p.array_s_texture)

# Ugly piece of code to display a numpy array texture
c = ctx.display_texture = context()
c.title = cell("str").set("Texture")
c.aspect_layout = pythoncell().fromfile("AspectLayout.py")
c.registrar.python.register(c.aspect_layout)
c.display_numpy = reactor({
    "array": {"pin": "input", "dtype": "array"},
    "title": {"pin": "input", "dtype": "str"},
})
c.registrar.python.connect("AspectLayout", c.display_numpy)
ctx.texture.connect(c.display_numpy.array)
c.title.connect(c.display_numpy.title)
c.display_numpy.code_update.set("update()")
c.display_numpy.code_stop.set("destroy()")
c.code = pythoncell()
c.code.connect(c.display_numpy.code_start)
c.code.fromfile("cell-display-numpy.py")
# /Ugly piece of code to display a texture


#Uniforms
ctx.uniforms = cell("json")
ctx.uniforms.connect(p.uniforms)
ctx.params_gen_uniforms = cell(("json", "seamless", "reactor_params"))
ctx.link_params_gen_uniforms = link(ctx.params_gen_uniforms, ".",
"params_gen_uniforms.json", file_dominant=file_dominant)
ctx.equilibrate()
ctx.gen_uniforms = reactor(ctx.params_gen_uniforms)
ctx.gravity = ctx.gen_uniforms.gravity.cell().set(1)
ctx.pointsize = ctx.gen_uniforms.pointsize.cell().set(40)
ctx.shrink_with_age = ctx.gen_uniforms.shrink_with_age.cell().set(True)

ctx.N.connect(ctx.gen_uniforms.N)
ctx.link_gen_uniforms_start = link(
    ctx.gen_uniforms.code_start.cell(),
    ".", "cell-gen-uniforms-start.py",
    file_dominant=file_dominant
)
ctx.link_gen_uniforms_update = link(
    ctx.gen_uniforms.code_update.cell(),
    ".", "cell-gen-uniforms-update.py",
    file_dominant=file_dominant
)
ctx.gen_uniforms.code_stop.cell().set("start_time = None")
ctx.gen_uniforms.uniforms.connect(ctx.uniforms)

# Signaling
ctx.period = cell("float").set(1.5)
# Repaint connection: has to be external, else it will be destroyed when ctx.program gets recreated
ctx.repaint = cell("signal")
p.painted.connect(ctx.repaint)
ctx.repaint.connect(p.update.cell())
# /repaint connection
p.painted.connect(ctx.gen_uniforms.update.cell())
ctx.timer = seamless.lib.timer(ctx.period)
t = ctx.timer.trigger.cell()
t.connect(ctx.gen_uniforms.reset.cell())
t.connect(ctx.gen_vertexdata.reset.cell())
ctx.init = seamless.lib.init()
t = ctx.init.trigger.cell()
t.connect(ctx.gen_uniforms.reset.cell())
t.connect(ctx.gen_vertexdata.reset.cell())

"""
for c in ctx.CHILDREN:
    if c.startswith("link_"):
        getattr(ctx, c).destroy()
"""

#Save
ctx.tofile("fireworks.seamless", backup=False)

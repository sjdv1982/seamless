from seamless import cell, pythoncell, context, reactor, transformer
from seamless.silk import Silk
from seamless.lib.gui.basic_editor import edit
from seamless.lib.gui.basic_display import display
from seamless.lib.filelink import link
from seamless.lib.gui.gl import glprogram

ctx = context()

# Vertexdata Silk model
ctx.silk_vertexdata = cell(("text", "code", "silk"))
ctx.link_silk_vertexdata = link(ctx.silk_vertexdata, ".", "vertexdata.silk")
ctx.registrar.silk.register(ctx.silk_vertexdata)

# Shaders
ctx.vert_shader = cell(("text", "code", "vertexshader"))
ctx.frag_shader = cell(("text", "code", "fragmentshader"))
ctx.link_vert_shader = link(ctx.vert_shader, ".", "vert_shader.glsl")
ctx.link_frag_shader = link(ctx.frag_shader, ".", "frag_shader.glsl")


# Program template
ctx.program_template = cell("cson")
ctx.link_program_template = link(ctx.program_template, ".", "program_template.cson")


# Program and program generator
ctx.program = cell("json")
ctx.display_program = display(ctx.program)
ctx.gen_program = transformer({"program_template": {"pin": "input", "dtype": "json"},
                               "program": {"pin": "output", "dtype": "json"}})
ctx.registrar.silk.connect("VertexData", ctx.gen_program)
ctx.link_gen_program = link(ctx.gen_program.code.cell(), ".", "cell-gen-program.py")
ctx.program_template.connect(ctx.gen_program.program_template)
ctx.gen_program.program.connect(ctx.program)

#GL program
ctx.equilibrate() #ctx.program has to be generated first
p = ctx.glprogram = glprogram(ctx.program)
ctx.frag_shader.connect(p.fragment_shader)
ctx.vert_shader.connect(p.vertex_shader)

# Vertexdata generator
ctx.N = cell("int").set(10000)
ctx.params_gen_vertexdata = cell(("json", "seamless", "transformer_params")).set(
 {
  "N": {
    "pin": "input",
    "dtype": "int"
  },
  "reset": {
    "pin": "input",
    "dtype": "signal"
  },
  "output": {
    "pin": "output",
    "dtype": "array"
  },
}
)
ctx.gen_vertexdata = transformer(ctx.params_gen_vertexdata)
ctx.N.connect(ctx.gen_vertexdata.N)
# does not work with live macro cells:
# ctx.registrar.silk.connect("VertexData", ctx.gen_vertexdata)
# ctx.registrar.silk.connect("VertexDataArray", ctx.gen_vertexdata)
ctx.registrar.silk.connect("VertexData", ctx.gen_vertexdata)
ctx.registrar.silk.connect("VertexDataArray", ctx.gen_vertexdata)
# ctx.registrar.silk.connect("VertexData", ctx) #?
# ctx.registrar.silk.connect("VertexDataArray", ctx) #?

ctx.vertexdata = cell("array")
ctx.vertexdata.set_store("GL")
ctx.gen_vertexdata.code.cell().set(
"""
assert N > 0
import numpy as np
data = np.zeros(N, VertexData.dtype)
data['a_lifetime'] = np.random.normal(2.0, 0.5, (N,))
start = data['a_startPosition']
end = data['a_endPosition']
start_values = np.random.normal(0.0, 0.2, (N, 3))
end_values = np.random.normal(0.0, 1.2, (N, 3))

# The following does not work in Numpy:
# start[:] = start_values
# end[:] = end_values
for n in range(3):
    field = ("x","y","z")[n]
    start[field] = start_values[:, n]
    end[field] = end_values[:, n]
data = VertexDataArray.from_numpy(data, copy=False, validate=False)
return data.numpy()
"""
)
ctx.gen_vertexdata.output.connect(ctx.vertexdata)
ctx.vertexdata.connect(p.array_vertexdata)

ctx.gen_texture_im1_params = cell(("json", "seamless", "transformer_params")).set(
 {
  "radius": {
    "pin": "input",
    "dtype": "int",
  },
  "output": {
    "pin": "output",
    "dtype": "array"
  }
}
)
ctx.im1 = cell("array")
ctx.im1.set_store("GLTex", 2)
ctx.gen_texture_im1 = transformer(ctx.gen_texture_im1_params)
ctx.gen_texture_im1.code.cell().set(
"""
import numpy as np

if 1:
    # Create a texture (random)
    im1 = 255 * np.ones(dtype=np.float32, shape=(2 * radius + 1, 2 * radius + 1, 3))
else:
    # Create a texture (from image)
    from PIL import Image
    im = Image.open("orca.png")
    im = im.resize((2 * radius + 1, 2 * radius + 1))
    im1 = np.asarray(im)

# Mask it with a disk
L = np.linspace(-radius, radius, 2 * radius + 1)
(X, Y) = np.meshgrid(L, L)
im1 = im1 * np.array((X ** 2 + Y ** 2) <= radius * radius)[:,:,None]

# Convert to float32 (optional)
if 0:
    im1 = np.array(im1, dtype="float32")/255

return im1
"""
)
radius = ctx.gen_texture_im1.radius.cell()
radius.set(32)
ctx.gen_texture_im1.output.connect(ctx.im1)
ctx.im1.connect(p.array_s_texture)


#Uniforms
ctx.uniforms = cell("json").set(
  {
    "u_time": 0.5,
    "u_centerPosition": (0,0,0),
    "u_color": (1,1,1,0.5),
    "u_pointsize": 40
  }
)
ctx.uniforms.connect(p.uniforms)

ctx.params_gen_uniforms = cell(("json", "seamless", "transformer_params")).set({
 "N": {
   "pin": "input",
   "dtype": "int"
 },
 "reset": {
    "pin": "input",
    "dtype": "signal"
 },
 "update": {
    "pin": "input",
    "dtype": "signal"
 },
 "updated": {
    "pin": "output",
    "dtype": "signal"
 },
 "uniforms": {
   "pin": "edit",
   "dtype": "json"
 },
}
)
ctx.gen_uniforms = reactor(ctx.params_gen_uniforms)
ctx.N.connect(ctx.gen_uniforms.N)
ctx.gen_uniforms.code_start.cell().set("""
import time
import numpy as np
start_time = None

def new_explosion():
    global start_time
    N = PINS.N.get()
    uniforms = {}

    # New centerpos
    centerpos = np.random.uniform(-0.5, 0.5, (3,))
    uniforms['u_centerPosition'] = tuple(centerpos)

    alpha = 1.0 / N ** 0.08
    color = np.random.uniform(0.1, 0.9, (3,))
    uniforms['u_color'] = tuple(color) + (alpha,)

    start_time = time.time()
    uniforms['u_time'] = 0
    PINS.uniforms.set(uniforms)

def update():
    if start_time is None:
        return
    uniforms = PINS.uniforms.get()
    curr_time = time.time() - start_time
    uniforms['u_time'] = curr_time
    PINS.uniforms.set(uniforms)
    PINS.updated.set()
""")

ctx.gen_uniforms.code_update.cell().set("""
if PINS.N.updated or PINS.reset.updated or start_time is None:
    new_explosion()
if PINS.update.updated:
    update()
""")

ctx.gen_uniforms.code_stop.cell().set("start_time = None")
ctx.gen_uniforms.uniforms.connect(ctx.uniforms)


p.rendered.cell().connect(ctx.gen_uniforms.update)
ctx.gen_uniforms.updated.cell().connect(p.update)

ctx.timer = reactor({
    "period": {"pin": "input", "dtype": "float"},
    "trigger": {"pin": "output", "dtype": "signal"}
})
ctx.timer.code_start.cell().set("""
from threading import Timer
dead = False
def trigger():
    global t
    if dead:
        return
    PINS.trigger.set()
    t = Timer(PINS.period.get(), trigger)
    t.setDaemon(True)
    t.start()
t = Timer(PINS.period.get(), trigger)
t.setDaemon(True)
t.start()
""")
ctx.timer.code_update.cell().set("")
ctx.timer.code_stop.cell().set("t.cancel(); dead = True")
ctx.timer.period.cell().set(1.5)
t = ctx.timer.trigger.cell()
t.connect(ctx.gen_uniforms.reset)
t.connect(ctx.gen_vertexdata.reset)

ctx.gen_vertexdata.reset.cell().set()
ctx.gen_uniforms.reset.cell().set()

import tempfile, os
tmpdir = os.path.join(tempfile.gettempdir(), "fireworks")
print("Edit the code in: ", tmpdir)
try:
    os.mkdir(tmpdir)
except FileExistsError:
    pass
ctx.link_vert = link(ctx.vert_shader, tmpdir, "Vertex_shader.glsl")
ctx.link_frag = link(ctx.frag_shader, tmpdir, "Fragment_shader.glsl")
ctx.link_silk_vertexdata = link(ctx.silk_vertexdata, tmpdir, "vertexdata.silk")
ctx.link_program_template = link(ctx.program_template, tmpdir, "program_template.cson")

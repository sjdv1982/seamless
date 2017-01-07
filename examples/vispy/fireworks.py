from seamless import cell, pythoncell, context, transformer, editor
from seamless.silk import Silk
from seamless.lib.hive.hiveprocess import hiveprocess

ctx = context()
ctx.c1 = cell(("text", "code", "silk")).fromfile("vertexdata.silk")
ctx.registrar.silk.register(ctx.c1)
#print(Silk.Vec3(1,2,3), ctx.registrar.silk.Vec3(3,4,5))

ctx.c2 = pythoncell().fromfile("fireworkhive.py")
ctx.registrar.hive.register(ctx.c2)
hp = ctx.hp = hiveprocess("fireworkhive")
hp.vert_shader.cell().fromfile("fireworks.vert")
hp.frag_shader.cell().fromfile("fireworks.frag")

ctx.gen_vertexbuffer_params = cell(("json", "seamless", "transformer_params")).set(
 {
  "N": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "object"
  },
  "VertexData" : {
    "pin": "registrar",
    "registrar": "silk"
  },
  "VertexDataArray" : {
    "pin": "registrar",
    "registrar": "silk"
  }
}
)
ctx.gen_vertexbuffer = transformer(ctx.gen_vertexbuffer_params)
N = ctx.gen_vertexbuffer.N.cell()
N.set(10000)
# does not work with live macro cells:
# ctx.registrar.silk.connect("VertexData", ctx.gen_vertexbuffer)
# ctx.registrar.silk.connect("VertexDataArray", ctx.gen_vertexbuffer)

ctx.gen_vertexbuffer.code.cell().set(
"""
assert N > 0
import numpy as np
data = np.zeros(N, VertexData.dtype)
data = VertexDataArray.from_numpy(data, copy=False, validate=False)
return data
"""
)
vertexbuffer = ctx.gen_vertexbuffer.output.cell()
vertexbuffer.connect(hp.vertexbuffer)


ctx.gen_texture_dict_params = cell(("json", "seamless", "transformer_params")).set(
 {
  "radius": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "object"
  }
}
)
ctx.gen_texture_dict = transformer(ctx.gen_texture_dict_params)
ctx.gen_texture_dict.code.cell().set(
"""
import numpy as np
# Create a texture
im1 = np.random.normal(
    0.8, 0.3, (radius * 2 + 1, radius * 2 + 1)).astype(np.float32)

# Mask it with a disk
L = np.linspace(-radius, radius, 2 * radius + 1)
(X, Y) = np.meshgrid(L, L)
im1 *= np.array((X ** 2 + Y ** 2) <= radius * radius, dtype='float32')
return {'s_texture': im1}
"""
)
radius = ctx.gen_texture_dict.radius.cell()
radius.set(32)
ctx.gen_texture_dict.output.cell().connect(hp.texture_dict)


#from hive.manager import hive_mode_as
#with hive_mode_as("build"):
    #hobj = FireWorkHive()

ctx.delay = cell("float").set(1.5)
ctx.delay.connect(hp.delay)

from seamless.lib.gui.basic_editor import edit
from seamless.lib.filelink import link

ctx.ed_delay = edit(ctx.delay, "Delay")
ctx.ed_radius = edit(radius, "Radius")
ctx.ed_N = edit(N, "N")
"""
ctx.ed_vert = edit(hp.vert_shader.cell(), "Vertex shader")
ctx.ed_frag = edit(hp.frag_shader.cell(), "Fragment shader")
ctx.ed_vertexformat = edit(ctx.c1, "Vertex format")
ctx.ed_hive = edit(ctx.c2, "Hive")
ctx.ed_gen_vertexbuffer = edit(ctx.gen_vertexbuffer.code.cell(),
  "Vertexbuffer generation")
ctx.ed_gen_texturedict = edit(ctx.gen_texture_dict.code.cell(),
  "Texture dict generation")
"""
ctx.ed_gen_vertexbuffer_params = edit(ctx.gen_vertexbuffer_params, "Vertexbuffer gen params")
ctx.ed_gen_texture_dict_params = edit(ctx.gen_texture_dict_params, "Texdict gen params")

import tempfile, os
#tmpdir = tempfile.mkdtemp()
tmpdir = os.path.join(tempfile.gettempdir(), "fireworks")
print("Edit the code in: ", tmpdir)
try:
    os.mkdir(tmpdir)
except FileExistsError:
    pass
ctx.ed_vert = link(hp.vert_shader.cell(), tmpdir, "Vertex_shader.glsl")
ctx.ed_frag = link(hp.frag_shader.cell(), tmpdir, "Fragment_shader.glsl")
ctx.ed_vertexformat = link(ctx.c1, tmpdir, "Vertex_format.silk")
ctx.ed_hive = link(ctx.c2, tmpdir, "Hive.py")
ctx.ed_gen_vertexbuffer = link(ctx.gen_vertexbuffer.code.cell(),
  tmpdir, "Vertexbuffer_generation.py")
ctx.ed_gen_texturedict = link(ctx.gen_texture_dict.code.cell(),
  tmpdir, "Texture_dict_generation.py")
#ctx.ed_gen_vertexbuffer_params = link(ctx.gen_vertexbuffer_params, tmpdir, "Vertexbuffer gen params")
#ctx.ed_gen_texture_dict_params = link(ctx.gen_texture_dict_params, tmpdir, "Texdict gen params")

#ctx.c2.set(ctx.c2.data.replace("800", "400"))

from seamless import cell, pythoncell, context, transformer, editor
from seamless.silk import Silk
from seamless.lib.hive.hiveprocess import hiveprocess

ctx = context()
c1 = cell(("text", "code", "silk")).fromfile("vertexdata.silk")
c1.set_context(ctx)
ctx.registrar.silk.register(c1)
#print(Silk.Vec3(1,2,3), ctx.registrar.silk.Vec3(3,4,5))

c2 = pythoncell().fromfile("fireworkhive.py")
c2.set_context(ctx)
ctx.registrar.hive.register(c2)
hp = ctx.processes.hp(hiveprocess("fireworkhive"))


hiveprocess_init = """
#HACK
from seamless.core.registrar import _registrars
hive_registrar = _registrars["hive"]
#/HACK
hive = hive_registrar.fireworkhive()
_cache["hive"] = hive
"""
hp.code_start.cell().set(hiveprocess_init)

hiveprocess_update = """
#HACK
hive = _cache["hive"]
push = ('vert_shader', 'vertexbuffer', 'texture_dict', 'frag_shader')
for a in push:
    if a in _updated:
        getattr(hive, a).push(globals()[a])
attr = ('delay',)
for a in attr:
    if a in _updated:
        setattr(hive, a, globals()[a])

"""
hp.code_update.cell().set(hiveprocess_update)

hiveprocess_stop = """
"""
hp.code_stop.cell().set(hiveprocess_stop)

hp.vert_shader.cell().fromfile("fireworks.vert")
hp.frag_shader.cell().fromfile("fireworks.frag")

gen_vertexbuffer_params = cell(("json", "seamless", "transformer_params")).set(
 {
  "N": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "object"
  }
}
)
gen_vertexbuffer_params.set_context(ctx)
gen_vertexbuffer = ctx.processes.gen_vertexbuffer(
 transformer(gen_vertexbuffer_params)
)
N = gen_vertexbuffer.N.cell()
N.set(10000)
gen_vertexbuffer.code.cell().set(
"""
assert N > 0
import numpy as np
from seamless.silk import Silk
data = np.zeros(N, Silk.VertexData.dtype)
data = Silk.VertexDataArray.from_numpy(data, copy=False, validate=False)
return data
"""
)
vertexbuffer = gen_vertexbuffer.output.cell()
vertexbuffer.connect(hp.vertexbuffer)


gen_texture_dict_params = cell(("json", "seamless", "transformer_params")).set(
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
gen_texture_dict_params.set_context(ctx)
gen_texture_dict = ctx.processes.gen_texture_dict(
  transformer(gen_texture_dict_params)
)
gen_texture_dict.code.cell().set(
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
radius = gen_texture_dict.radius.cell()
radius.set(32)
gen_texture_dict.output.cell().connect(hp.texture_dict)


#from hive.manager import hive_mode_as
#with hive_mode_as("build"):
    #hobj = FireWorkHive()

delay = ctx.cells.delay("float").set(1.5)
delay.connect(hp.delay)

from seamless.lib.gui.basic_editor import basic_editor, edit

ed_delay = edit(delay, "Delay")
ed_radius = edit(radius, "Radius")
ed_N = edit(N, "N")
ed_vert = edit(hp.vert_shader.cell(), "Vertex shader")
ed_frag = edit(hp.frag_shader.cell(), "Fragment shader")
ed_vertexformat = edit(c1, "Vertex format")
ed_hive = edit(c2, "Hive")
ed_gen_vertexbuffer = edit(gen_vertexbuffer.code.cell(),
  "Vertexbuffer generation")
ed_gen_vertexbuffer_params = edit(gen_vertexbuffer_params, "Vertexbuffer gen params")
ed_gen_texturedict = edit(gen_texture_dict.code.cell(),
  "Texture dict generation")
ed_gen_texture_dict_params = edit(gen_texture_dict_params, "Texdict gen params")

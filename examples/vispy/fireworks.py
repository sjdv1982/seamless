from seamless import cell, pythoncell, context, transformer, editor
from seamless.silk import Silk
from seamless.lib.hive.hiveprocess import hiveprocess

ctx = context()
c = cell(("text", "code", "silk")).fromfile("vertexdata.silk")
ctx.registrar.silk.register(c)
#print(Silk.Vec3(1,2,3), ctx.registrar.silk.Vec3(3,4,5))

c = pythoncell().fromfile("fireworkhive.py")
ctx.registrar.hive.register(c)
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


gen_vertexbuffer = ctx.processes.gen_vertexbuffer(transformer(
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
))
gen_vertexbuffer.N.cell().set(10000)
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

gen_texture_dict = ctx.processes.gen_texture_dict(transformer(
 {
  "radius": {
    "pin": "input",
    "dtype": "float"
  },
  "output": {
    "pin": "output",
    "dtype": "object"
  }
}
))
gen_texture_dict.code.cell().set(
"""
import numpy as np
# Create a texture
im1 = np.random.normal(
    0.8, 0.3, (int(radius) * 2 + 1, int(radius) * 2 + 1)).astype(np.float32)

# Mask it with a disk
L = np.linspace(-radius, radius, 2 * radius + 1)
(X, Y) = np.meshgrid(L, L)
im1 *= np.array((X ** 2 + Y ** 2) <= radius * radius, dtype='float32')
return {'s_texture': im1}
"""
)
gen_texture_dict.radius.cell().set(32)
gen_texture_dict.output.cell().connect(hp.texture_dict)


#from hive.manager import hive_mode_as
#with hive_mode_as("build"):
    #hobj = FireWorkHive()



delay = ctx.cells.delay("float").set(1.5)
delay.connect(hp.delay)

from seamless.lib.gui.basic_editor import basic_editor, edit
edd = edit(delay)
import sys; sys.exit()

#Editor
int_editor_code = """
from seamless.qt.QtWidgets import QSpinBox, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle('Test editor')
w.resize(300,100)
w.show()
b = QSpinBox()
b.setMaximum(1000000)
vbox.addWidget(b)
b.valueChanged.connect(output.set)
_cache["b"] = b
_cache["w"] = w
"""

float_editor_code = """
from seamless.qt.QtWidgets import QDoubleSpinBox, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle('Test editor')
w.resize(300,100)
w.show()
b = QDoubleSpinBox()
b.setSingleStep(0.1)
b.setMaximum(10)
vbox.addWidget(b)
b.valueChanged.connect(output.set)
_cache["b"] = b
_cache["w"] = w
"""

tparams = {
  "value": {
    "pin": "input",
    "dtype": "int"
  },
  "output": {
    "pin": "output",
    "dtype": "int"
  }
}
tparams2 = {
  "value": {
    "pin": "input",
    "dtype": "float"
  },
  "output": {
    "pin": "output",
    "dtype": "float"
  }
}

ed1 = ctx.processes.ed1(editor(tparams))
ed1.code_start.cell().set(int_editor_code)
ed1.code_stop.cell().set('_cache["w"].destroy()')
ed1.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
b.setValue(value)
w.setWindowTitle("N")
"""
)
c = gen_vertexbuffer.N.cell()
c.connect(ed1.value)
ed1.output.solid.connect(c)

ed2 = ctx.processes.ed2(editor(tparams2))
ed2.code_start.cell().set(float_editor_code)
ed2.code_stop.cell().set('_cache["w"].destroy()')
ed2.code_update.cell().set("""
b, w = _cache["b"], _cache["w"]
b.setValue(value)
w.setWindowTitle("Delay")
"""
)
delay.connect(ed2.value)
ed2.output.solid.connect(delay)

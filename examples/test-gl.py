import seamless
from seamless import context, cell, reactor
from seamless.lib.filelink import link
from seamless.lib.gui.gl import glprogram
import numpy as np

ctx = context()

# Build data
"""
data = np.zeros(4, [("position", np.float32, 2),
                         ("color",    np.float32, 4)])
"""
data = np.zeros(4, [("position", [('x', np.float32), ('y', np.float32)]),
                    ("color", [('r', np.float32), ('g', np.float32), ('b', np.float32), ('a', np.float32)])
                   ])

data['color'] = [(1, 0, 0, 1), (0, 1, 0, 1),
                      (0, 0, 1, 1), (1, 1, 0, 1)]
data['position'] = [(-1, -1), (-1, +1),
                         (+1, -1), (+1, +1)]
indices = np.array((1,2,3,0,1,2),dtype=np.uint16)


c = ctx.array_default = cell("array")
c.set_store("GL")
c.set(data)

c = ctx.array_indices = cell("array")
c.set_store("GL")
c.set(indices)

# Shaders
vertex_code = """
    uniform float scale;
    attribute vec4 color;
    attribute vec2 position;
    varying vec4 v_color;
    void main()
    {
        gl_Position = vec4(scale*position, 0.0, 1.0);
        v_color = color;
    } """

fragment_code = """
    varying vec4 v_color;
    void main()
    {
        gl_FragColor = v_color;
    } """

ctx.vertex_shader = cell(("text", "code", "vertexshader")).set(vertex_code)
ctx.fragment_shader = cell(("text", "code", "fragmentshader")).set(fragment_code)

glstate = dict(
    clear=True,
    clear_color='black',
    depth_test=False,
    blend=True,
    blend_func=('src_alpha', 'one')
)


# Program
program = {
  "arrays": ["default"],
  "uniforms": {
    "scale": "float",
  },
  "render": {
    "command": "triangle_strip",
    "glstate": glstate,
    "attributes": {
      "position": {
        "dtype": "vec2",
        "array": "default",
        "rae": "['position'][:]",
      },
      "color": {
        "dtype": "vec4",
        "array": "default",
        "rae": "['color'][:]",
      },
    }
  },
}

program2 = {
  "arrays": ["default", "indices"],
  "uniforms": {
    "scale": "float",
  },
  "render": {
    "command": "triangles",
    "glstate": glstate,
    "attributes": {
      "position": {
        "dtype": "vec2",
        "array": "default",
        "rae": "['position'][:]",
      },
      "color": {
        "dtype": "vec4",
        "array": "default",
        "rae": "['color'][:]",
      },
    },
    "indices": {
      "dtype": "short",
      "array": "indices",
    }
  }
}

ctx.program = cell("json").set(program)
#ctx.program = cell("json").set(program2)

p = ctx.glprogram = glprogram(ctx.program)
ctx.vertex_shader.connect(p.vertex_shader)
ctx.fragment_shader.connect(p.fragment_shader)
ctx.array_default.connect(p.array_default)

ctx.uniforms = cell("json").set({"scale": 1.0})
ctx.uniforms.connect(p.uniforms)

ctx.program.set(program2)
ctx.array_indices.connect(p.array_indices)
ctx.equilibrate()

#Saving doesn't work: independent array cells, and we don't save stores...
#import os
#ctx.tofile(os.path.splitext(__file__)[0] + ".seamless", backup=False)

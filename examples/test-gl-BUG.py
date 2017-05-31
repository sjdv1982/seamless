import seamless
from seamless import context, cell, reactor, transformer
from seamless.lib.gui.gl import glprogram
import numpy as np

ctx = context()

# Shaders
vertex_code = """
    void main()
    {
        gl_Position = vec4(1.0, 1.0, 1.0, 1.0);
    } """

fragment_code = """
    void main()
    {
        gl_FragColor = vec4(1.0, 1.0, 1.0, 1.0);;
    } """

ctx.vertex_shader = cell(("text", "code", "vertexshader")).set(vertex_code)
ctx.fragment_shader = cell(("text", "code", "fragmentshader")).set(fragment_code)

# Program
program = {
  "arrays": ["default"],
  "uniforms": {},
  "render": {
    "command": "points",
    "glstate": {},
    "attributes": {},
  },
}

ctx.pre_program = cell("json").set(program)
ctx.gen_program = transformer({"program": {"pin": "input", "dtype": "json"},
                                "result": {"pin": "output", "dtype": "json"}})
ctx.pre_program.connect(ctx.gen_program.program)
ctx.gen_program.code.cell().set("return program")
ctx.program = ctx.gen_program.result.cell()
ctx.equilibrate()

p = ctx.glprogram = glprogram(ctx.program)
p.uniforms.cell().set({})
ctx.vertex_shader.connect(p.vertex_shader)
ctx.fragment_shader.connect(p.fragment_shader)

data = np.zeros(4, [("position", np.float32, 2),
                         ("color",    np.float32, 4)])
ctx.data = cell("array")
ctx.data.set(data)
ctx.data.set_store("GL")
ctx.data.connect(p.array_default)

p.rendered.cell().connect(p.update)

"""
BUG:
ctx.program.touch() will always re-create the window
ctx.pre_program.touch() will once-in-a-while result in a Qt crash
This is much more likely if ctx.program.touch() has not occurred yet,
 and if the GL window has not been killed beforehand
"""

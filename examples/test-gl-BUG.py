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
  "arrays": [],
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

p.rendered.cell().connect(p.update) #if this connection is broken, no more crash!

"""
BUG:
ctx.program.touch() will always re-create the window
ctx.pre_program.touch() will once-in-a-while result in a Qt crash
This is much more likely if ctx.program.touch() has not occurred yet,
 and if the GL window has not been killed beforehand

PARTIAL SOLUTION: let Qt flush its event loop whenever work is done
This solves the issue for the current program.
But this does not solve the same issue in fireworks.py...
Remove run_qt() in seamless/init.py:run_work to reproduce the bug

FULL SOLUTION: in addition, forbid QOpenGLWidget to call self.update()
 from within self.paintGL (._painting attribute to check this)
See cell-glwindow.py in lib/gui/gl.
This prevents all crashes, but it must be combined with the partial
solution above, else the window will freeze.

As of now, no more issues.
"""

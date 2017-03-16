print("TEST-NEW0")

import numpy as np
from OpenGL.arrays import vbo
from OpenGL.GL import shaders
from OpenGL.GL import *
from OpenGL import GL as gl

from GLStore import GLStore, GLSubStore
from Renderer import Renderer, VertexAttribute

initialized = False
print("TEST-NEW")

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

def init():
    global data, program, dummy1, dummy2, loc_scale, renderer, initialized

    if initialized:
        return
    # Build data
    data = np.zeros(4, [("position", np.float32, 2),
                             ("color",    np.float32, 4)])
    data['color'] = [(1, 0, 0, 1), (0, 1, 0, 1),
                          (0, 0, 1, 1), (1, 1, 0, 1)]
    data['position'] = [(-1, -1), (-1, +1),
                             (+1, -1), (+1, +1)]

    vertex_shader = shaders.compileShader(vertex_code, GL_VERTEX_SHADER)

    fragment_shader = shaders.compileShader(fragment_code, GL_FRAGMENT_SHADER)

    program = shaders.compileProgram(vertex_shader, fragment_shader)
    shaders.glUseProgram(program)

    class dummy:
        pass
    dummy1 = dummy(); dummy1.data = data
    store = GLStore(dummy1)
    store.bind()

    mapping = {
        "command": "triangle_strip",
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
    }
    storedict = {"default": store}
    print(storedict["default"].parent().data)

    #
    indices = np.array((1,2,3,0,1,2),dtype=np.uint16)
    dummy2=dummy(); dummy.data = indices
    storedict["indices"] = GLStore(dummy2)
    storedict["indices"].bind()
    print(storedict["indices"].parent().data)
    mapping["indices"] = {
                        "dtype": "short",
                        "array": "indices",
                    }
    mapping["command"] = "triangles_indexed"

    #
    renderer = Renderer(mapping, program, storedict)
    print(storedict["indices"].parent().data)
    print(storedict["default"].parent().data)
    renderer.bind()

    # Bind uniforms
    # --------------------------------------
    loc_scale = gl.glGetUniformLocation(program, "scale")
    print(loc_scale)
    print("INIT")
    initialized = True

def paint():
    #print("DRAW")
    glEnable(GL_BLEND)
    glDisable(GL_DEPTH_TEST)
    glClear(GL_COLOR_BUFFER_BIT)
    gl.glUniform1f(loc_scale, 1.0)
    renderer.draw()

def do_update():
    global initialized
    if PINS.init.updated:
        initialized = False
        init()
    if PINS.paint.updated:
        if not initialized:
            init()
        paint()

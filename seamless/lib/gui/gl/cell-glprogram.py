import numpy as np
from OpenGL.arrays import vbo
from OpenGL.GL import shaders
from OpenGL.GL import *
from OpenGL import GL as gl

from seamless.lib.gui.gl.set_uniform import set_uniform

from seamless.lib.gui.gl.Renderer import Renderer, VertexAttribute
from seamless.lib.gui.gl import glstate as glstate_module

initialized = False
shader_program = None
renderer = False
uniform_types = {}
uniform_locations = {}
uniform_values = {}
uniform_dirty = set()

def init():
    global initialized, shader_program, renderer, uniform_types, \
     glstate, glclear
    from seamless.dtypes.gl import GLStore, GLTexStore

    if initialized:
        return

    # Compile shaders
    vertex_code = PINS.vertex_shader.get()
    fragment_code = PINS.fragment_shader.get()
    vertex_shader = shaders.compileShader(vertex_code, GL_VERTEX_SHADER)
    fragment_shader = shaders.compileShader(fragment_code, GL_FRAGMENT_SHADER)
    shader_program = shaders.compileProgram(vertex_shader, fragment_shader)

    program = PINS.program.get()

    # Bind vertex attributes
    storedict = {}
    for ar in program["arrays"]:
        attr = "array_" + ar
        store = getattr( getattr(PINS, attr), "store", None)
        assert isinstance(store, GLStore), ar #TODO: nicer error message
        #store.bind() #superfluous
        storedict[ar] = store

    # Bind textures
    texdict = {}
    for ar in program.get("textures",[]):
        attr = "array_" + ar
        store = getattr( getattr(PINS, attr), "store", None)
        assert isinstance(store, GLTexStore), ar #TODO: nicer error message
        #store.bind() #superfluous
        texdict[ar] = store

    # Create renderer and set glstate
    render = program["render"]
    glstate = render["glstate"]
    glclear = glstate.pop("clear", True)
    renderer = Renderer(render, shader_program, storedict, texdict)
    renderer.bind()

    # Get uniform bindings
    shaders.glUseProgram(shader_program)
    uniform_locations.clear()
    uniform_dirty.clear()
    uniform_types = program.get("uniforms", {})
    for uniform in uniform_types:
        loc = gl.glGetUniformLocation(shader_program, uniform)
        if loc == -1:
            print("WARNING: unknown uniform '%s'" % uniform)
            continue
        uniform_locations[uniform] = loc
        uniform_dirty.add(uniform)

    initialized = True

def paint():
    #print("DRAW")
    if not initialized:
        init()
    shaders.glUseProgram(shader_program)

    for uniform in list(uniform_dirty):
        if uniform not in uniform_locations:
            continue
        if uniform not in uniform_types:
            continue
        utype = uniform_types[uniform]
        value = uniform_values.get(uniform, None)
        if value is None:
            print("WARNING: unset uniform '%s'", uniform)
            continue
        loc = uniform_locations[uniform]
        set_uniform(value, utype, loc)
        uniform_dirty.remove(uniform)

    glstate_module.set_state(**glstate)
    if glclear not in (None, False):
        if glclear == True:
            glstate_module.clear()
        else:
            glstate_module.clear(*glclear)
    renderer.draw()
    PINS.rendered.set()

def do_update():
    global initialized

    #NOTE: Except if "init" or "paint" has just been updated,
    #  we are not guaranteed to have an active OpenGL context!!
    # Therefore, we have to use "dirty" flags, rather than direct GL commands!

    arrays = PINS.program.get()["arrays"]
    textures = PINS.program.get().get("textures", [])

    dirty_renderer = False
    repaint = False
    for ar in arrays + textures:
        attr = "array_" + ar
        pin = getattr(PINS, attr)
        if pin.updated:
            dirty_renderer = True

    if PINS.init.updated:
        initialized = False
        init()
        dirty_renderer = False

    if PINS.uniforms.updated:
        new_uniform_values = PINS.uniforms.get()
        for uniform in new_uniform_values:
            v_old = uniform_values.get(uniform, None)
            v_new = new_uniform_values.get(uniform, None)
            if v_old != v_new:
                uniform_values[uniform] = v_new
                uniform_dirty.add(uniform)
                repaint = True

    if PINS.paint.updated:
        paint()

    if PINS.program.updated:
        initialized = False
        repaint = True

    if initialized and dirty_renderer:
        renderer.set_dirty()
        repaint = True

    if repaint and not PINS.paint.updated:
        PINS.repaint.set()

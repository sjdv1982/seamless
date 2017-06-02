from collections import OrderedDict
import numpy as np
from OpenGL.arrays import vbo
from OpenGL.GL import shaders
from OpenGL.GL import *
from OpenGL import GL as gl

from seamless import opengl
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
texture_locations = OrderedDict()
warnings = []

def init():
    global initialized, shader_program, renderer, uniform_types, \
     glstate, glclear, texdict
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
    texture_locations.clear()
    for ar in program.get("textures",[]):
        attr = "array_" + ar
        store = getattr( getattr(PINS, attr), "store", None)
        assert isinstance(store, GLTexStore), ar #TODO: nicer error message
        #store.bind() #superfluous
        texdict[ar] = store
        loc = gl.glGetUniformLocation(shader_program, ar)
        if loc == -1:
            print("WARNING: unknown texture '%s'" % ar)
            continue
        texture_locations[ar] = loc

    # Create renderer and set glstate
    render = program["render"]
    glstate = render["glstate"]
    glclear = glstate.pop("clear", True)
    renderer = Renderer(render, shader_program, storedict)
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

    old_warnings = warnings[:]
    warnings.clear()

    #re-bind the textures every draw, to be safe
    for texnr, tex in enumerate(texture_locations):
        gl.glActiveTexture(gl.GL_TEXTURE0+texnr)
        loc = texture_locations[tex]
        gl.glUniform1i(loc, texnr)
        store = texdict[tex]
        store.bind()

    for uniform in list(uniform_dirty):
        if uniform not in uniform_locations:
            continue
        if uniform not in uniform_types:
            continue
        utype = uniform_types[uniform]
        value = uniform_values.get(uniform, None)
        if value is None:
            warnings.append("WARNING: unset uniform '%s'" % uniform)
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

    # Heisenbug!!! see below. Seems to be solved now
    try:
        warnings
    except NameError:
        return

    if warnings != old_warnings:
        for warning in warnings:
            print(warning)
    #print("/DRAW")

def do_update():
    global initialized

    """
    Outside of "init" and "paint", we have to use "dirty" flags,
     rather than direct GL commands!
    """

    updated = set()
    for attr in PINS.__dict__:
        pin = getattr(PINS, attr)
        if hasattr(pin, "updated") and pin.updated:
            updated.add(attr)


    arrays = PINS.program.get()["arrays"]
    textures = PINS.program.get().get("textures", [])

    gl_context = opengl()

    dirty_renderer = False
    repaint = False
    for ar in arrays + textures:
        attr = "array_" + ar
        pin = getattr(PINS, attr)
        if pin.updated:
            dirty_renderer = True

    if PINS.init.updated:
        initialized = False
        if gl_context:
            init()
        else:
            PINS.init.unclear()

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
        if gl_context:
            paint()
            repaint = False
        else:
            repaint = True

    # Heisenbug!!! see test-gl-BUG.py
    # As of now, seems to be solved, see cell-glwindow.py
    try:
        initialized
    except NameError:
        import sys
        msg = """seamless/lib/gui/cell-glprogram.py
Something has gone wrong, PyQt has corrupted Python's memory
A crash will now happen... no idea why, sorry
"""
        print(msg, file=sys.stderr)
        return
    # /heisenbug

    if PINS.program.updated or \
      PINS.vertex_shader.updated or PINS.fragment_shader.updated:
        initialized = False
        repaint = True

    if initialized and dirty_renderer:
        renderer.set_dirty()
        repaint = True

    if repaint:
        PINS.repaint.set()

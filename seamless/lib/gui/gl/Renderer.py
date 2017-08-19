import numpy as np
from OpenGL import GL as gl
import ctypes
from collections import OrderedDict
from seamless.dtypes.gl import GLSubStore
import threading

class VertexAttribute:
    def __init__(self, attribute, glsl_dtype, shader_program, store, *,
            instanced=False):
        self.attribute = attribute
        self.glsl_dtype = glsl_dtype
        self.shader_program = shader_program
        self.store = store
        self.instanced = instanced
        self.length = None
        self.enabled = False

    def verify_dtype(self):
        glsl_dtype, dtype, shape = self.glsl_dtype, self.store.dtype, self.store.shape
        def get_fields():
            if dtype.fields is None:
                return [(dtype, 0)]
            fieldnames = [d[0] for d in  dtype.descr]
            fields = [dtype.fields[f] for f in fieldnames]
            fields = [(f[0], f[1]) for f in fields]
            return fields

        ok = False
        if glsl_dtype == "vec4":
            if len(shape) == 1:
                refe_fields = [(np.float32, 4*n) for n in range(4)]
                fields = get_fields()
                if fields == refe_fields:
                    ok = True
            elif len(shape) == 2:
                if dtype == np.float32 and shape[1] == 4:
                    ok = True
        elif glsl_dtype == "vec3":
            if len(shape) == 1:
                refe_fields = [(np.float32, 4*n) for n in range(3)]
                fields = get_fields()
                if fields == refe_fields:
                    ok = True
            elif len(shape) == 2:
                if dtype == np.float32 and shape[1] == 3:
                    ok = True
        elif glsl_dtype == "vec2":
            if len(shape) == 1:
                refe_fields = [(np.float32, 4*n) for n in range(2)]
                fields = get_fields()
                if fields == refe_fields:
                    ok = True
            elif len(shape) == 2:
                if dtype == np.float32 and shape[1] == 2:
                    ok = True
        elif glsl_dtype == "float":
            if len(shape) == 1:
                if dtype == np.float32:
                    ok = True
        elif glsl_dtype == "int":
            if len(shape) == 1:
                if dtype == np.int32:
                    ok = True
        if not ok:
            raise TypeError(self.attribute, glsl_dtype, dtype, len(shape)) #TODO: other GLSL types

    def bind(self):
        assert threading.current_thread() is threading.main_thread()
        if self.length:
            self.unbind()
        if self.glsl_dtype == "vec4":
            size, dtype = 4, gl.GL_FLOAT
        elif self.glsl_dtype == "vec3":
            size, dtype = 3, gl.GL_FLOAT
        elif self.glsl_dtype == "vec2":
            size, dtype = 2, gl.GL_FLOAT
        elif self.glsl_dtype == "float":
            size, dtype = 1, gl.GL_FLOAT
        else:
            raise TypeError(self.glsl_dtype)
        self.verify_dtype()
        self.store.bind()
        offset = self.store.offset
        stride = self.store.strides[0]
        buf = self.store.opengl_id
        loc = gl.glGetAttribLocation(self.shader_program, self.attribute)
        if loc == -1:
            print("WARNING: unused attribute '%s'" % self.attribute)
            self.enabled = False
        else:
            gl.glEnableVertexAttribArray(loc)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buf)
            gl.glVertexAttribPointer(loc, size, dtype, False, stride, ctypes.c_void_p(offset))
            if self.instanced:
                gl.glVertexAttribDivisor(loc,1)
            self.enabled = True
        self.length = self.store.shape[0]

    def unbind(self):
        assert threading.current_thread() is threading.main_thread()
        if self.enabled:
            loc = gl.glGetAttribLocation(self.shader_program, self.attribute)
            gl.glDisableVertexAttribArray(loc)

class IndexArray:
    def __init__(self, dtype, shader_program, store):
        assert dtype in ("int", "short", "byte"), dtype
        self.dtype = dtype
        if dtype == "int":
            self.gl_dtype = gl.GL_UNSIGNED_INT
        elif dtype == "short":
            self.gl_dtype = gl.GL_UNSIGNED_SHORT
        elif dtype == "byte":
            self.gl_dtype = gl.GL_UNSIGNED_BYTE

        self.shader_program = shader_program
        self.store = store
        self.length = None

    def verify_dtype(self):
        my_dtype, dtype, shape = self.dtype, self.store.dtype, self.store.shape

        ok = False
        if my_dtype == "int":
            np_dtype = np.uint
        elif my_dtype == "short":
            np_dtype = np.uint16
        elif my_dtype == "byte":
            np_dtype = np.uint8

        ok = False
        if len(shape) == 1:
            if np_dtype == dtype:
                ok = True
        if not ok:
            raise TypeError(my_dtype, dtype, len(shape))

    def bind(self):
        #the bind will last indefinitely, not just until GL_ARRAY_BUFFER is re-bound
        assert threading.current_thread() is threading.main_thread()
        if self.length:
            self.unbind()
        self.verify_dtype()
        self.store.bind()
        offset = self.store.offset
        stride = self.store.strides[0]
        assert stride == self.store.itemsize, "Index array must be contiguous in memory"
        buf = self.store.opengl_id
        assert buf > 0

        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, buf)
        self.offset = offset
        self.length = self.store.shape[0]

    def unbind(self):
        assert threading.current_thread() is threading.main_thread()
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)

class Renderer:
    def __init__(self, render, shader_program, storedict):
        self.shader_program = shader_program
        self.attributes = {}
        self.indices = None
        self.length = None
        self.command = render["command"]
        self.vao = None
        self.dirty = False
        self.instanced = False
        assert self.command in (
            "points",
            "lines",
            "triangles",
            "triangle_strip", "triangle_fan"
            )
        if "indices" in render:
            assert "indices" in render
            at = render["indices"]
            store = storedict[at["array"]]
            rae = at.get("rae", None)
            if rae is None:
                substore = store
            else:
                substore = GLSubStore(ar, rae)
            self.indices = IndexArray(at["dtype"], shader_program, substore)
        if "instanced" in render:
            self.instanced = render["instanced"]

        for atname, at in render["attributes"].items():
            store = storedict[at["array"]]
            rae = at.get("rae", None)
            instanced = at.get("instanced", False)
            if instanced:
                assert self.instanced
            if rae is None:
                substore = store
            else:
                substore = GLSubStore(store, rae)
            vertex_attribute = VertexAttribute(atname, at["dtype"],
              shader_program, substore, instanced=instanced)
            self.attributes[atname] = vertex_attribute

    def bind(self):
        assert threading.current_thread() is threading.main_thread()
        length = None
        first_atname = None
        if self.instanced:
            instances = None
            instanced_first_atname = None
        vao = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(vao)
        if self.indices:
            self.indices.bind()
        for atname, at in self.attributes.items():
            at.bind()
            if at.instanced:
                if instances is None:
                    instances = at.length
                    instanced_first_atname = atname
                if instances != at.length:
                    raise ValueError((instanced_first_atname, instances), (atname, at.length))
            else:
                if length is None:
                    length = at.length
                    first_atname = atname
                if length != at.length:
                    raise ValueError((first_atname, length), (atname, at.length))
        if length is None:
            length = 0
        if self.instanced:
            self.instances = instances
        self.length = length
        self.vao = vao
        self.dirty = False

    def set_dirty(self):
        self.dirty = True

    def draw(self):
        assert threading.current_thread() is threading.main_thread()
        if self.dirty or not self.vao:
            self.bind()
        gl.glBindVertexArray(self.vao)
        indexed = (self.indices is not None)
        if self.command == "points":
            mode = gl.GL_POINTS
        elif self.command == "lines":
            mode = gl.GL_LINES
        elif self.command == "triangles":
            mode = gl.GL_TRIANGLES
        elif self.command == "triangle_strip":
            mode = gl.GL_TRIANGLE_STRIP
        elif self.command == "triangle_fan":
            mode = gl.GL_TRIANGLE_FAN
        else:
            raise ValueError(self.command)
        if not indexed:
            if not self.instanced:
                gl.glDrawArrays(mode, 0, self.length)
            else:
                gl.glDrawArraysInstanced(mode, 0, self.length, self.instances)
        else:
            if not self.instanced:
                gl.glDrawElements(mode, self.indices.length,
                  self.indices.gl_dtype, ctypes.c_void_p(self.indices.offset))
            else:
                gl.glDrawElementsInstanced(mode, self.indices.length,
                  self.indices.gl_dtype, ctypes.c_void_p(self.indices.offset),
                  self.instances)

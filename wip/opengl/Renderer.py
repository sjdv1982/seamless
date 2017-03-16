import numpy as np
from OpenGL import GL as gl
import ctypes
from collections import OrderedDict
from GLStore import GLSubStore

class VertexAttribute:
    def __init__(self, attribute, glsl_dtype, program, store):
        self.attribute = attribute
        self.glsl_dtype = glsl_dtype
        self.program = program
        self.store = store
        self.length = None

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

        if not ok:
            raise TypeError(glsl_dtype, dtype, len(shape))

    def bind(self):
        if self.length:
            self.unbind()
        if self.glsl_dtype == "vec4":
            size, dtype = 4, gl.GL_FLOAT
        elif self.glsl_dtype == "vec3":
            size, dtype = 3, gl.GL_FLOAT
        elif self.glsl_dtype == "vec2":
            size, dtype = 2, gl.GL_FLOAT
        else:
            raise TypeError(self.glsl_dtype)
        self.verify_dtype()
        offset = self.store.offset
        stride = self.store.strides[0]
        buf = self.store.opengl_id
        loc = gl.glGetAttribLocation(self.program, self.attribute)
        gl.glEnableVertexAttribArray(loc)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buf)
        gl.glVertexAttribPointer(loc, size, dtype, False, stride, ctypes.c_void_p(offset))
        self.length = self.store.shape[0]

    def unbind(self):
        loc = gl.glGetAttribLocation(self.program, self.attribute)
        gl.glDisableVertexAttribArray(loc)


class IndexArray:
    def __init__(self, dtype, program, store):
        assert dtype in ("int", "short", "byte"), dtype
        self.dtype = dtype
        if dtype == "int":
            self.gl_dtype = gl.GL_UNSIGNED_INT
        elif dtype == "short":
            self.gl_dtype = gl.GL_UNSIGNED_SHORT
        elif dtype == "byte":
            self.gl_dtype = gl.GL_UNSIGNED_BYTE

        self.program = program
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
        if self.length:
            self.unbind()
        self.verify_dtype()
        offset = self.store.offset
        stride = self.store.strides[0]
        assert stride == self.store.itemsize, "Index array must be contiguous in memory"
        buf = self.store.opengl_id

        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, buf)
        self.offset = offset
        self.length = self.store.shape[0]

    def unbind(self):
        loc = gl.glGetAttribLocation(self.program, self.attribute)
        gl.glDisableVertexAttribArray(loc)

class Renderer:
    def __init__(self, mapping, program, storedict):
        self.program = program
        self.attributes = {}
        self.indices = None
        self.length = None
        self.command = mapping["command"]
        self.vao = None
        assert self.command in (
            "triangles", "triangle_strip",
            "triangles_indexed"
            )
        if self.command.endswith("indexed"):
            assert "indices" in mapping
            at = mapping["indices"]
            store = storedict[at["array"]]
            rae = at.get("rae", None)
            if rae is None:
                substore = store
            else:
                substore = GLSubStore(ar, rae)
            self.indices = IndexArray(at["dtype"], program, substore)
        else:
            assert "indices" not in mapping

        for atname, at in mapping["attributes"].items():
            store = storedict[at["array"]]
            rae = at.get("rae", None)
            if rae is None:
                substore = store
            else:
                substore = GLSubStore(store, rae)
            vertex_attribute = VertexAttribute(atname, at["dtype"], program, substore)
            self.attributes[atname] = vertex_attribute

    def bind(self):
        length = None
        first_atname = None
        vao = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(vao)
        if self.indices:
            self.indices.bind()
        for atname, at in self.attributes.items():
            at.bind()
            if length is None:
                length = at.length
                first_atname = atname
            if length != at.length:
                raise ValueError((first_atname, length), (atname, at.length))
        self.length = length
        self.vao = vao

    def draw(self):
        #TODO: draw flags (depth test, etc.)
        if not self.vao:
            self.bind()  #TODO: re-bind when store gets updated/re-bound
        gl.glBindVertexArray(self.vao)
        print(self.length)
        if self.command == "triangle_strip":
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, self.length)
        elif self.command == "triangles":
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, self.length)
        elif self.command == "triangles_indexed":
            gl.glDrawElements(gl.GL_TRIANGLES, self.indices.length,
              self.indices.gl_dtype, ctypes.c_void_p(self.indices.offset))

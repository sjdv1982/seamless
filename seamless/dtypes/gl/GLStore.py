import weakref
from OpenGL import GL as gl
import numpy as np
import weakref
import re
import ctypes
import threading
from . import _ctypes
from .gloo.glir import gl_types, gl_get_alignment, as_enum

class GLStoreBase:
    _opengl_context = None
    def sanity_check(self):
        from PyQt5.QtGui import QOpenGLContext
        context = QOpenGLContext.currentContext()
        assert context
        assert threading.current_thread() is threading.main_thread()
        if self._opengl_context is not None:
            #assert context is self._opengl_context
            if context is not self._opengl_context:
                self.destroy()
                self.create()

class GLSubStore(GLStoreBase):
    regexp = re.compile("\[.*?\]")
    def __init__(self, parent, expression):
        self.parent = weakref.ref(parent)
        self._expression = expression
        self._ast = self._parse_expression(expression)

        self._state = None

    @classmethod
    def _parse_expression(self, expression):
        exc = "Malformed expression: '{0}'".format(expression)
        matches = list(self.regexp.finditer(expression))
        if len(matches) == 0:
            expressions = [expression]
        else:
            start = 0
            expressions = []
            for match in matches:
                match_start, match_end = match.span()
                if match_start != start:
                    raise ValueError(exc)
                expressions.append(match.group()[1:-1])
                start = match_end
        ast = []
        for expression in expressions:
            subexpressions = expression.split(",")
            if len(subexpressions) == 1:
                subexpr = subexpressions[0].strip()
                prop = True
                if ":" in subexpr:
                    prop = False
                else:
                    try:
                        int(subexpr)
                        prop = False
                    except ValueError:
                        pass
                if prop:
                    propname = subexpr
                    flanks = propname[0], propname[-1]
                    if flanks[0] == flanks[1] and flanks[0] in ('"', "'"):
                        propname = propname[1:-1]
                    ast.append(propname)
                    continue
            sub_ast = []
            for slice_ in subexpressions:
                subslices = slice_.split(":")
                if len(subslices) == 1:
                    index_string = slice_
                    try:
                        index = int(index_string)
                        sub_ast.append(index)
                    except ValueError:
                        raise ValueError(exc)
                    continue
                slice_terms = []
                for subslice in subslices:
                    subslice = subslice.strip()
                    if not len(subslice):
                        slice_terms.append(None)
                    else:
                        try:
                            index = int(subslice)
                            slice_terms.append(index)
                        except ValueError:
                            raise ValueError(exc)
                sub_ast.append(slice(*slice_terms))
            ast.append(tuple(sub_ast))

        return ast

    @property
    def opengl_id(self):
        return self.parent().opengl_id

    @property
    def dtype(self):
        self.resolve()
        return self._subdata.dtype

    @property
    def shape(self):
        self.resolve()
        return self._subdata.shape

    @property
    def strides(self):
        self.resolve()
        return self._subdata.strides

    @property
    def itemsize(self):
        return self._subdata.itemsize

    @property
    def offset(self):
        self.resolve()
        ptr_self = self._subdata.ctypes.data
        ptr_base = self._subdata.base.ctypes.data
        return ptr_self - ptr_base

    @property
    def dirty(self):
        return self.parent().dirty
    def set_dirty(self):
        self.parent().set_dirty()

    def bind(self):
        assert threading.current_thread() is threading.main_thread()
        self.parent().bind()

    def _update(self):
        pdata = self.parent().parent().data
        data = pdata
        for term in self._ast:
            data = data[term]
        self._subdata = data

    def resolve(self):
        p = self.parent()
        parent_state = p._state
        if parent_state is None:
            self._state = None
            return None
        if self._state != parent_state:
            self._update()
            self._state = parent_state
        return self._state

class GLStore(GLStoreBase):
    usage = gl.GL_DYNAMIC_DRAW
    init_params = {}
    def __init__(self, parent):
        self.parent = weakref.ref(parent)
        self._dirty = True
        self._id = None
        self._state = 0
        #_state always progresses by 1, whenever the buffer is updated

    @property
    def opengl_id(self):
        return self._id

    @property
    def dirty(self):
        return self._dirty
    def set_dirty(self):
        self._dirty = True

    @property
    def dtype(self):
        return self.parent().data.dtype

    @property
    def shape(self):
        return self.parent().data.shape

    @property
    def strides(self):
        return self.parent().data.strides

    @property
    def offset(self):
        return 0

    @property
    def itemsize(self):
        return self.parent().data.itemsize

    def bind(self):
        from PyQt5.QtGui import QOpenGLContext
        self.sanity_check()
        if not self._dirty:
            return
        if self._id is None:
            self.create()
        elif self._state:
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._id)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, 0, None, self.usage)
        arr = self.parent().data
        assert arr is not None and isinstance(arr, np.ndarray)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._id)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, arr.nbytes, arr, self.usage)
        self._dirty = False
        self._state += 1

    def create(self):
        from PyQt5.QtGui import QOpenGLContext
        self._id = gl.glGenBuffers(1)
        context = QOpenGLContext.currentContext()
        self._opengl_context = context
        from seamless import add_opengl_destructor
        add_opengl_destructor(context, self.destroy)

    def destroy(self):
        #print("GLStore DESTROY")
        try:
            assert threading.current_thread() is threading.main_thread()
            if self._id is not None:
                gl.glDeleteBuffers(1, [self._id])
        finally:
            self._id = None
            self._dirty = True
            self._opengl_context = None

class GLTexStore(GLStoreBase):
    def __init__(self, parent, dimensions):
        self.init_params = {"dimensions": dimensions}
        from .gloo import Texture1D, Texture2D, Texture3D
        self.parent = weakref.ref(parent)
        if dimensions == 1:
            self._target = gl.GL_TEXTURE_1D
            self._textureclass = Texture1D
        elif dimensions == 2:
            self._target = gl.GL_TEXTURE_2D
            self._textureclass = Texture2D
        elif dimensions == 3:
            self._target = gl.GL_TEXTURE_3D
            self._textureclass = Texture3D

        self._dirty = set(["data"])
        self._id = None
        self._state = 0
        self._texture = None
        #_state always progresses by 1, whenever the buffer is updated
        self._shape_formats = None

    @property
    def opengl_id(self):
        return self._id

    @property
    def dirty(self):
        return len(self._dirty)
    def set_dirty(self):
        self._dirty.add("data")

    @property
    def dtype(self):
        return self.parent().data.dtype

    @property
    def shape(self):
        return self.parent().data.shape

    @property
    def strides(self):
        return self.parent().data.strides

    @property
    def offset(self):
        return 0

    @property
    def itemsize(self):
        return self.parent().data.itemsize

    def create(self):
        from PyQt5.QtGui import QOpenGLContext
        self._id = gl.glGenTextures(1)
        context = QOpenGLContext.currentContext()
        self._opengl_context = context
        from seamless import add_opengl_destructor
        add_opengl_destructor(context, self.destroy)

    def bind(self):
        from PyQt5.QtGui import QOpenGLContext
        self.sanity_check()
        if self._id is None:
            self.create()

        gl.glBindTexture(self._target, self._id)
        if not len(self._dirty):
            return

        #for now, recreate a new Texture object whenever something is dirty
        arr = self.parent().data
        self._texture = self._textureclass(self, arr)

        self._dirty = set()
        self._state += 1

    def set_size(self, shape, format, internalformat, unsigned):
        self.sanity_check()
        gl.glBindTexture(self._target, self._id)
        format = as_enum(format)
        internalformat = format if internalformat is None \
            else as_enum(internalformat)
        byte = gl.GL_UNSIGNED_BYTE if unsigned else gl.GL_BYTE
        self._shape_formats = shape, format, internalformat
        gl.glBindTexture(self._target, self._id)
        if self._target == gl.GL_TEXTURE_1D:
            func = gl.glTexImage1D
            shape2 = shape[:1]
        elif self._target == gl.GL_TEXTURE_2D:
            func = gl.glTexImage2D
            shape2 = shape[:2]
        elif self._target == gl.GL_TEXTURE_3D:
            func = gl.glTexImage3D
            shape2 = shape[:3]
        shape2 = tuple(reversed(shape2))
        args = (self._target, 0, internalformat) + shape2 + \
                    (0, format, byte, None)
        func(*args)


    def set_data(self, offset, data):
        self.sanity_check()
        gl.glBindTexture(self._target, self._id)
        shape, format, internalformat = self._shape_formats

        # Get gtype
        gtype = gl_types.get(np.dtype(data.dtype), None)
        if gtype is None:
            raise ValueError("Type %r not allowed for texture" % data.dtype)

        offset2 = np.array(offset)
        assert offset2.dtype == np.int, offset
        if self._target == gl.GL_TEXTURE_1D:
            alignment = gl_get_alignment(data.shape[-1])
            func = gl.glTexSubImage1D
            shape2 = shape[:1]
            assert offset2.shape == (1,), offset
        elif self._target == gl.GL_TEXTURE_2D:
            alignment = gl_get_alignment(data.shape[-2]*data.shape[-1])
            func = gl.glTexSubImage2D
            shape2 = shape[:2]
            assert offset2.shape == (2,), offset
        elif self._target == gl.GL_TEXTURE_3D:
            alignment = gl_get_alignment(data.shape[-3] *
                                            data.shape[-2] * data.shape[-1])
            func = gl.glTexSubImage3D
            shape2 = shape[:3]
            assert offset2.shape == (3,), offset

        # Set alignment (width is nbytes_per_pixel * npixels_per_line)
        if alignment != 4:
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, alignment)

        # Upload
        if not data.flags['C_CONTIGUOUS']:
            data = data.copy('C')
        #p = data.ctypes.data_as(ctypes.POINTER(_ctypes[data.dtype]))
        p = data.tobytes()
        args = (self._target, 0) + \
                tuple(reversed(offset2)) + \
                shape2 + \
               (format, gtype, p)
        func(*args)

        # Set alignment back
        if alignment != 4:
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)

    def set_wrapping(self, wrapping):
        self.sanity_check()
        gl.glBindTexture(self._target, self._id)
        wrapping = [as_enum(w) for w in wrapping]
        if len(wrapping) == 3:
            GL_TEXTURE_WRAP_R = 32882
            gl.glTexParameterf(self._target, GL_TEXTURE_WRAP_R, wrapping[0])
        if len(wrapping) >= 2:
            gl.glTexParameterf(self._target,
                               gl.GL_TEXTURE_WRAP_S, wrapping[-2])
        gl.glTexParameterf(self._target, gl.GL_TEXTURE_WRAP_T, wrapping[-1])

    def set_interpolation(self, min, mag):
        self.sanity_check()
        gl.glBindTexture(self._target, self._id)
        min, mag = as_enum(min), as_enum(mag)
        gl.glTexParameterf(self._target, gl.GL_TEXTURE_MIN_FILTER, min)
        gl.glTexParameterf(self._target, gl.GL_TEXTURE_MAG_FILTER, mag)

    def destroy(self):
        #print("GLTexStore DESTROY")
        try:
            assert threading.current_thread() is threading.main_thread()
            if self._id is not None:
                gl.glDeleteTextures(self._id)
        finally:
            self._id = None
            self._dirty = set("data")
            self._opengl_context = None



#TODO: add nicer destroy

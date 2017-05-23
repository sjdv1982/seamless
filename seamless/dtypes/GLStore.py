import weakref
from OpenGL import GL
import numpy as np
import weakref
import re

class GLStoreBase:
    pass

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
        raise AttributeError

    def _update(self):
        pdata = self.parent().parent().data
        data = pdata
        for term in self._ast:
            data = data[term]
        self._subdata = data

    def resolve(self):
        p = self.parent()
        p.bind()
        parent_state = p._state
        if parent_state is None:
            self._state = None
            return None
        if self._state != parent_state:
            self._update()
            self._state = parent_state
        return self._state

class GLStore(GLStoreBase):
    usage = GL.GL_DYNAMIC_DRAW
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
        if not self._dirty:
            return
        if self._id is None:
            self._id = GL.glGenBuffers(1)
        elif self._state:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._id)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, self.usage)
        arr = self.parent().data
        assert arr is not None and isinstance(arr, np.ndarray)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._id)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, arr.nbytes, arr, self.usage)
        self._dirty = False
        self._state += 1

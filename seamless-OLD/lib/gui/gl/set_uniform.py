# -*- coding: utf-8 -*-
# Taken and adapted from vispy/gloo/glir.py and vispy/gloo/program.py
# -----------------------------------------------------------------------------
# Copyright (c) 2015, Vispy Development Team. All Rights Reserved.
# Distributed under the (new) BSD License. See vispy/LICENSE.txt for more info.
# -----------------------------------------------------------------------------

from OpenGL import GL as gl
import numpy as np
import ctypes

from seamless.dtypes.gl import _ctypes, _gtypes

UTYPEMAP = {
    'float': 'glUniform1f',
    'vec2': 'glUniform2f',
    'vec3': 'glUniform3f',
    'vec4': 'glUniform4f',
    'int': 'glUniform1i',
    'ivec2': 'glUniform2i',
    'ivec3': 'glUniform3i',
    'ivec4': 'glUniform4i',
    'bool': 'glUniform1i',
    'bvec2': 'glUniform2i',
    'bvec3': 'glUniform3i',
    'bvec4': 'glUniform4i',
    'mat2': 'glUniformMatrix2fv',
    'mat3': 'glUniformMatrix3fv',
    'mat4': 'glUniformMatrix4fv',
}


def set_uniform(value, type_, handle):
    """ Set a uniform value. Value is assumed to have been checked.
    """
    dtype, count = _gtypes[type_]

    # Look up function to call
    funcname = UTYPEMAP[type_]
    func = getattr(gl, funcname)
    cdtype = _ctypes[dtype]
    arr = np.array(value, dtype=dtype,ndmin=1)

    # Triage depending on type
    if type_.startswith('mat'):
        # Value is matrix, these gl funcs have alternative signature
        transpose = False  # OpenGL ES 2.0 does not support transpose
        p = arr.ctypes.data_as(ctypes.POINTER(cdtype))
        func(handle, 1, transpose, p)
    else:
        # Regular uniform
        assert arr.shape == (count,), (value, count, arr.shape)
        #v = (cdtype*len(arr))(*arr)
        #print(value, [v[n] for n in range(count)] )
        #print(func, count, arr)
        func(handle, *arr)

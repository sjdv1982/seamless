import ctypes, numpy as np
_ctypes = {
    np.float32: ctypes.c_float,
    np.int32: ctypes.c_int32,
    np.uint8: ctypes.c_uint8,

    np.dtype("float32"): ctypes.c_float,
    np.dtype("int32"): ctypes.c_int32,
    np.dtype("uint8"): ctypes.c_uint8,
}

_gtypes = {  # DTYPE, NUMEL
    'float':        (np.float32, 1),
    'vec2':         (np.float32, 2),
    'vec3':         (np.float32, 3),
    'vec4':         (np.float32, 4),
    'int':          (np.int32,   1),
    'ivec2':        (np.int32,   2),
    'ivec3':        (np.int32,   3),
    'ivec4':        (np.int32,   4),
    'bool':         (np.int32,   1),
    'bvec2':        (np.bool,    2),
    'bvec3':        (np.bool,    3),
    'bvec4':        (np.bool,    4),
    'mat2':         (np.float32, 4),
    'mat3':         (np.float32, 9),
    'mat4':         (np.float32, 16),
    'sampler1D':    (np.uint32, 1),
    'sampler2D':    (np.uint32, 1),
    'sampler3D':    (np.uint32, 1),
}

from .GLStore import GLStoreBase, GLStore, GLSubStore, GLTexStore
from .color import Color

# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Taken from vispy/gloo/glir.py
# Copyright (c) 2015, Vispy Development Team. All Rights Reserved.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
# -----------------------------------------------------------------------------

import os
import sys
import re
import json
import weakref
string_types = (str, bytes)

import numpy as np

from OpenGL import GL as gl

class Enum(int):
    ''' Enum (integer) with a meaningful repr. '''
    def __new__(cls, name, value):
        base = int.__new__(cls, value)
        base.name = name
        return base
    def __repr__(self):
        return self.name

# TODO: expose these via an extension space in .gl?
_internalformats = [
    Enum('GL_RED', 6403),
    Enum('GL_R', 8194),
    Enum('GL_R8', 33321),
    Enum('GL_R16', 33322),
    Enum('GL_R16F', 33325),
    Enum('GL_R32F', 33326),
    Enum('GL_RG', 33319),
    Enum('GL_RG8', 333323),
    Enum('GL_RG16', 333324),
    Enum('GL_RG16F', 333327),
    Enum('GL_RG32F', 33328),
    Enum('GL_RGB', 6407),
    Enum('GL_RGB8', 32849),
    Enum('GL_RGB16', 32852),
    Enum('GL_RGB16F', 34843),
    Enum('GL_RGB32F', 34837),
    Enum('GL_RGBA', 6408),
    Enum('GL_RGBA8', 32856),
    Enum('GL_RGBA16', 32859),
    Enum('GL_RGBA16F', 34842),
    Enum('GL_RGBA32F', 34836)
]
_internalformats = dict([(enum.name, enum) for enum in _internalformats])

def as_enum(enum):
    """ Turn a possibly string enum into an integer enum.
    """
    if isinstance(enum, string_types):
        try:
            enum = getattr(gl, 'GL_' + enum.upper())
        except AttributeError:
            try:
                enum = _internalformats['GL_' + enum.upper()]
            except KeyError:
                raise ValueError('Could not find int value for enum %r' % enum)
    return enum

gl_types = {
    np.dtype(np.int8): gl.GL_BYTE,
    np.dtype(np.uint8): gl.GL_UNSIGNED_BYTE,
    np.dtype(np.int16): gl.GL_SHORT,
    np.dtype(np.uint16): gl.GL_UNSIGNED_SHORT,
    np.dtype(np.int32): gl.GL_INT,
    np.dtype(np.uint32): gl.GL_UNSIGNED_INT,
    np.dtype(np.float16) : gl.GL_HALF_FLOAT,
    np.dtype(np.float32): gl.GL_FLOAT,
    np.dtype(np.float64) : gl.GL_DOUBLE
}

# Taken from pygly
def gl_get_alignment(width):
    """Determines a textures byte alignment.

    If the width isn't a power of 2
    we need to adjust the byte alignment of the image.
    The image height is unimportant

    www.opengl.org/wiki/Common_Mistakes#Texture_upload_and_pixel_reads
    """
    # we know the alignment is appropriate
    # if we can divide the width by the
    # alignment cleanly
    # valid alignments are 1,2,4 and 8
    # put 4 first, since it's the default
    alignments = [4, 8, 2, 1]
    for alignment in alignments:
        if width % alignment == 0:
            return alignment

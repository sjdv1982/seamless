#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vispy: gallery 20

"""
Example demonstrating simulation of fireworks using point sprites.
(adapted from the "OpenGL ES 2.0 Programming Guide")

This example demonstrates a series of explosions that last one second. The
visualization during the explosion is highly optimized using a Vertex Buffer
Object (VBO). After each explosion, vertex data for the next explosion are
calculated, such that each explosion is unique.
"""

import os
import numpy as np
from seamless import silk
from seamless.silk import Silk
currdir = os.path.dirname(__file__)


# Create a texture
radius = 32.0
im1 = np.random.normal(
    0.8, 0.3, (radius * 2 + 1, radius * 2 + 1)).astype(np.float32)

# Mask it with a disk
L = np.linspace(-radius, radius, 2 * radius + 1)
(X, Y) = np.meshgrid(L, L)
im1 *= np.array((X ** 2 + Y ** 2) <= radius * radius, dtype='float32')

# Set number of particles, you should be able to scale this to 100000
N = 10000

# Create vertex data container
silkmodel = os.path.join(currdir, open("vertexdata.silk").read())
silk.register(silkmodel)

from seamless.silk.registers.minischemas import _minischemas
data = np.zeros(N, Silk.VertexData.dtype)
data = Silk.VertexDataArray.from_numpy(data)

VERT_SHADER = open(os.path.join(currdir, "fireworks.vert")).read()
FRAG_SHADER = open(os.path.join(currdir, "fireworks.frag")).read()
from fireworkhive import fireworkhive

if __name__ == '__main__':
    from vispy import app
    h = fireworkhive()
    h.vert_shader.push(VERT_SHADER)
    h.frag_shader.push(FRAG_SHADER)
    h.vertexbuffer.push(data)
    h.texture_dict.push({'s_texture': im1})
    h.canvas.title = "FireWorkHive"
    h.delay = 1.5
    app.run()

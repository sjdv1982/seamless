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

import time
import os
import numpy as np
from seamless import silk
from seamless.silk import Silk
import hive
from canvashive import CanvasHive
currdir = os.path.dirname(__file__)


# Create a texture
radius = 32
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

def build_fireworkhive(i, ex, args):
    ex.canvas = CanvasHive(keys='interactive', size=(800, 600))
    i.starttime = hive.attribute(data_type="float")

    def draw(self):
        program = self.canvas.program
        currtime = time.time()
        if self._starttime is None or currtime - self._starttime > self.delay:
            self.new_explosion()

        # Draw
        program['u_time'] = time.time() - self._starttime
        program.draw('points')
    i.draw = hive.modifier(draw)
    hive.connect(ex.canvas.draw, i.draw)

    def new_explosion(self):
        program = self.canvas.program
        if program is None:
            return
        vertexbuffer = self.canvas.v_vertexbuffer
        # New centerpos
        centerpos = np.random.uniform(-0.5, 0.5, (3,))
        program['u_centerPosition'] = centerpos

        # New color, scale alpha with N
        N = len(vertexbuffer)
        alpha = 1.0 / N ** 0.08
        color = np.random.uniform(0.1, 0.9, (3,))

        program['u_color'] = tuple(color) + (alpha,)

        # Create new vertex data
        p = vertexbuffer.make_numpy()
        p['a_lifetime'] = np.random.normal(2.0, 0.5, (N,))
        start = p['a_startPosition']
        end = p['a_endPosition']
        start_values = np.random.normal(0.0, 0.2, (N, 3))
        end_values = np.random.normal(0.0, 0.2, (N, 3))
        # The following does not work in Numpy:
        # start[:] = start_values
        # end[:] = end_values
        for n in range(3):
            field = ("x","y","z")[n]
            start[field] = start_values[:, n]
            end[field] = end_values[:, n]

        # Set time to zero
        self._starttime = time.time()
    i.new_explosion = hive.modifier(new_explosion)
    hive.trigger(ex.canvas.program_rebuilt, i.new_explosion)

    #make new_explosion triggerable from the outside
    i.t_new_explosion = hive.triggerfunc(i.new_explosion)
    ex.new_explosion = hive.hook(i.t_new_explosion)
    ex.delay = hive.attribute(data_type="float", start_value=1.5)

    #export the canvas parameters
    ex.vert_shader = hive.antenna(ex.canvas.vert_shader)
    ex.frag_shader = hive.antenna(ex.canvas.frag_shader)
    ex.texture_dict = hive.antenna(ex.canvas.texture_dict)
    ex.vertexbuffer = hive.antenna(ex.canvas.vertexbuffer)
    #ex.title = hive.antenna(ex.canvas.title)

FireWorkHive = hive.hive("FireWorkHive", build_fireworkhive)

if __name__ == '__main__':
    from vispy import app
    h = FireWorkHive()
    h.vert_shader.push(VERT_SHADER)
    h.frag_shader.push(FRAG_SHADER)
    h.vertexbuffer.push(data)
    h.texture_dict.push({'s_texture': im1})
    h.canvas.title = "FireWorkHive"
    h.delay = 1.5
    app.run()

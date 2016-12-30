import hive
import numpy as np
import time
from seamless.lib.hive.canvashive import canvashive
from vispy import gloo

def build_fireworkhive(i, ex, args):
    ex.canvas = canvashive(keys='interactive', size=(800, 600))
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

        program.bind(gloo.VertexBuffer(p))
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

fireworkhive = hive.hive("fireworkhive", build_fireworkhive)

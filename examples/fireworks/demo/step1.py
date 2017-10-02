from seamless.lib.gui.gl import glprogram

ctx.vertexdata = cell("array")

# Generate three-dimensional points (even though we will ignore Z)
N = 10000
import numpy as np
values = np.random.normal(0.0, 0.2, (N, 3))
ctx.vertexdata.set(values)

# Discretize manually
im = np.zeros((500,500))
values_xy = (values[:,:2]*250+250).astype(int)
im[values_xy[:,0], values_xy[:,1]] = 1
ctx.im = cell("array").set(im)

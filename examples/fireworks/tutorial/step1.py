from seamless.lib.gui.gl import glprogram

ctx.vertexdata = cell("array")

# Generate three-dimensional points (even though we will ignore Z)
N = 10000
import numpy as np
values = np.random.normal(0.0, 0.2, (N, 3)).astype(np.float32)
ctx.vertexdata.set(values)

#add a bar in the lower right corner
bar = [(n,nn,0) for nn in np.arange(-0.8, -0.7, 0.001) \
  for n in np.arange(0.3, 0.7, 0.001) ]
values = np.concatenate((values, bar)).astype(np.float32)
ctx.vertexdata.set(values)

# Discretize manually
im = np.zeros((480,640)) #in an image, the first dim is Y!
values_x = (values[:,0]*320+320).astype(int)
values_x = np.minimum(values_x, 640)
values_y = (values[:,1]*240+240).astype(int)
values_y = np.minimum(values_y, 480)
im[values_y, values_x] = 1
im[::-1,:] = im #in an image, Y goes from top to bottom!

ctx.im = cell("array").set(im)

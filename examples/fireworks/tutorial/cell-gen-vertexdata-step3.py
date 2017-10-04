# Generate three-dimensional points (even though we will ignore Z)
import numpy as np
values = np.random.normal(0.0, 0.2, (N, 3)).astype(np.float32)

#add a bar in the lower right corner
bar = [(n,nn,0) for nn in np.arange(-0.8, -0.7, 0.001) \
  for n in np.arange(0.3, 0.7, 0.001) ]
values = np.concatenate((values, bar)).astype(np.float32)
return values

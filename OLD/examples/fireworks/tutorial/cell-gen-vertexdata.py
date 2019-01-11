# Generate three-dimensional points (even though we will ignore Z)
assert N > 0
import numpy as np

data = np.zeros(N, VertexData.dtype)
data['a_lifetime'] = np.random.normal(1.0, 0.5, (N,))
start = data['a_startPosition']
end = data['a_endPosition']

rotmask = np.rot90(mask, 3) #in (x,y) form
start_values0 = np.random.random((1000000, 3))
p = (start_values0*len(mask)).astype(np.int)[:,:2]
mask_values = rotmask[p[:,0], p[:,1]]
start_values0 = start_values0[mask_values==0]
start_values = 2*start_values0[:N]-1
end_values = np.random.normal(0.0, 0.15, (N, 3))

for n in range(3):
    field = ("x","y","z")[n]
    start[field] = start_values[:, n]
    end[field] = end_values[:, n]

# if we want to work at the Silk level:
# data = VertexDataArray.from_numpy(data, copy=False, validate=False)
# return data.numpy()

return data

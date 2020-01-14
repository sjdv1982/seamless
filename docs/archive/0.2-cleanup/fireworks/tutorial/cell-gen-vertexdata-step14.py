# Generate three-dimensional points (even though we will ignore Z)
assert N > 0
import numpy as np

data = np.zeros(N, VertexData.dtype)
data['a_lifetime'] = np.random.normal(1.0, 0.5, (N,))
start = data['a_startPosition']
end = data['a_endPosition']

# The following does not work in Numpy:
#start[:] = np.random.normal(0.0, 0.2, (N, 3))
#end[:] = np.random.normal(0.0, 0.7, (N, 3))
start_values = np.random.normal(0.0, 0.2, (N, 3))
end_values = np.random.normal(0.0, 0.7, (N, 3))
for n in range(3):
    field = ("x","y","z")[n]
    start[field] = start_values[:, n]
    end[field] = end_values[:, n]

# if we want to work at the Silk level:
# data = VertexDataArray.from_numpy(data, copy=False, validate=False)
# return data.numpy()

return data

assert N > 0
import numpy as np
data = np.zeros(N, VertexData.dtype)
data['a_lifetime'] = np.random.normal(2.0, 0.5, (N,))
start = data['a_startPosition']
end = data['a_endPosition']
start_values = np.random.normal(0.0, 0.2, (N, 3))
end_values = np.random.normal(0.0, 1.2, (N, 3))

# The following does not work in Numpy:
# start[:] = start_values
# end[:] = end_values
for n in range(3):
    field = ("x","y","z")[n]
    start[field] = start_values[:, n]
    end[field] = end_values[:, n]
data = VertexDataArray.from_numpy(data, copy=False, validate=False)
return data.numpy()

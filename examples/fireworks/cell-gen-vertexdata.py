assert N > 0
import numpy as np
data = np.zeros(N, VertexData.dtype)
data['a_lifetime'] = np.random.normal(2.0, 0.5, (N,))
start = data['a_startPosition']
end = data['a_endPosition']
colors = data['a_color']
start_values = np.random.normal(0.0, 0.2, (N, 3))
end_values = np.random.normal(0.0, 0.7, (N, 3))
color_values = np.random.uniform(0.0, 1.0, (N, 3))

# The following does not work in Numpy:
# start[:] = start_values
# end[:] = end_values
for n in range(3):
    field = ("x","y","z")[n]
    start[field] = start_values[:, n]
    end[field] = end_values[:, n]
    colors[field] = color_values[:, 0]
data = VertexDataArray.from_numpy(data, copy=False, validate=False)
return data.numpy()

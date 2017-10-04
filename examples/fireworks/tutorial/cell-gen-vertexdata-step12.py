# Generate three-dimensional points (even though we will ignore Z)
import numpy as np

dtype = np.dtype([
    ('a_startPosition', np.float32, 3),
    ('a_endPosition', np.float32, 3),
])
data = np.zeros(N, dtype)
start = data['a_startPosition']
end = data['a_endPosition']
start[:] = np.random.normal(0.0, 0.2, (N, 3))
end[:] = np.random.normal(0.0, 0.7, (N, 3))

return data

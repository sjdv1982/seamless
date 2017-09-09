import numpy as np
assert len(normals) == len(coordinates)
dtype = [("position", np.float32, 3), ("color", np.float32, 3)]

vector_factor = 0.1

e = len(edges)
c = len(coordinates)
lines = np.zeros(e+6*c, dtype=dtype)
l = lines[:e]
l["position"] = np.take(coordinates, edges,axis=0)
l["color"] = (1, 1, 1)

l = lines[e:e+2*c]
l["position"][::2] = coordinates
l["position"][1::2] = coordinates + normals * vector_factor
l["color"] = (1, 1, 0)

l = lines[e+2*c:e+4*c]
l["position"][::2] = coordinates
l["position"][1::2] = coordinates + tangents[:,0,:] * vector_factor
l["color"] = (1, 0, 0)

l = lines[e+4*c:e+6*c]
l["position"][::2] = coordinates
l["position"][1::2] = coordinates + tangents[:,1,:] * vector_factor
l["color"] = (0, 0, 1)

return lines

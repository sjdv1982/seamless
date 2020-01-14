import numpy as np
from numpy.linalg import norm
from plyfile import PlyData, make2d
import zipfile

filename = PINS.filename.get()

if filename.endswith(".zip"):
    zipf = zipfile.ZipFile(filename)
    assert len(zipf.namelist()) == 1
    zply = zipf.open(zipf.namelist()[0])
    plydata = PlyData.read(zply)
else:
    plydata = PlyData.read(filename)
elements = {e.name: e for e in plydata.elements}
vertices = elements["vertex"].data
faces = elements["face"].data

#faces => indices + edges
indices = make2d(faces['vertex_indices']).astype(np.uint16)
assert indices.shape[1] == 3 #triangles only
edges = set()
for triangle in indices:
    for p1,p2 in ((0,1),(1,2),(2,0)):
        i1, i2 = triangle[p1], triangle[p2]
        if i2 < i1: i1,i2 = i2,i1
        edges.add((i1,i2))
edges = np.array(list(edges),dtype=np.uint16)

#vertices => coordinates + normals
for n in range(len(vertices.dtype)):
    assert vertices.dtype[n] == vertices.dtype[0]
vertices = vertices.view(vertices.dtype[0]).reshape(vertices.shape + (-1,))
coordinates = vertices[:,:3]
normals = vertices[:,3:6]
coordinates -= coordinates.mean(axis=0)

# Calculate triangle coordinates and normals
triangle_indices = indices.flatten()
c = triangle_coordinates = coordinates[triangle_indices] \
    .reshape(indices.shape+(3,))
v1 = c[:,1] - c[:,0]
v1 /= norm(v1,axis=1)[:,None]
v2 = c[:,2] - c[:,0]
v2 /= norm(v2,axis=1)[:,None]
triangle_normals = np.cross(v1, v2)
triangle_normals /= norm(triangle_normals, axis=1)[:, None]
triangle_normals = np.repeat(triangle_normals, 3, axis=0)
triangle_coordinates = triangle_coordinates.reshape(
    (len(triangle_indices), 3) )

# Write out arrays
PINS.coordinates.set(coordinates)
PINS.normals.set(normals)
PINS.edges.set(edges.flatten())
PINS.triangle_indices.set(triangle_indices)
PINS.triangle_coordinates.set(triangle_coordinates)
PINS.triangle_normals.set(triangle_normals)

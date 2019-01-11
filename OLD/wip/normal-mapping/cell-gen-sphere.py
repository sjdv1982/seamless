import numpy as np
from numpy.linalg import norm

subdivisions = PINS.subdivisions.get()
minimizations = PINS.minimizations.get()

# Initialize a tetrahedron
p = 2**-0.5
f = p
fp=p*f
coordinates = np.array((
    (f, 0, -fp),
    (-f, 0, -fp),
    (0, f, fp),
    (0, -f, fp)
), dtype="float32")
edges = np.array( [(i,j) for i in range(4) for j in range(i+1,4)],
                    dtype=np.uint16)
indices = np.array( [[0,1,2], [0,2,3], [0,3,1], [1,3,2] ],
                    dtype=np.uint16)

for n in range(subdivisions):
    offset = len(coordinates)

    # Calculate vertexpair-to-edgeindex mapping
    edge_map = {(e[0],e[1]): enr for enr,e in enumerate(edges)}
    edge_map.update( {(e[1],e[0]): enr for enr,e in enumerate(edges)} )
    # Calculate edge centers
    edge_coordinates = coordinates[edges.flatten()] \
        .reshape((len(edges), 2, 3))
    edge_centers = np.sum(edge_coordinates,axis=1)/2
    # Cut all edges in two
    coordinates = np.concatenate( (coordinates, edge_centers) )
    edges = np.concatenate((edges, edges))
    e = np.arange(len(edge_centers)) + offset
    edges[:len(edge_centers), 1] = e
    edges[len(edge_centers):, 0] = e
    #Using the cut edges, replace every triangle by four new ones
    new_indices = []
    new_edges = []
    for triangle_nr, triangle_indices in enumerate(indices):
        i = triangle_indices
        e1 = edge_map[i[0], i[1]]
        e2 = edge_map[i[1], i[2]]
        e3 = edge_map[i[0], i[2]]
        ee1 = e1 + offset
        ee2 = e2 + offset
        ee3 = e3 + offset
        new_indices += [
            [i[0], ee1, ee3],
            [i[1], ee2, ee1],
            [i[2], ee3, ee2],
            [ee1, ee2, ee3],
        ]
        new_edges += [
            [ee1, ee2],
            [ee2, ee3],
            [ee3, ee1],
        ]
    # Replace the triangle indices, append the edges
    indices = np.array(new_indices, dtype=np.uint16)
    new_edges = np.array(new_edges, dtype=np.uint16)
    edges = np.concatenate( (new_edges, edges) )
    # After the second subdivision, remove the first 4 vertices,
    #  and all edges and triangles of which they are a part
    if n == 1:
        coordinates = coordinates[4:]
        edges = edges[np.min(edges,axis=1) >= 4] - 4
        indices = indices[np.min(indices,axis=1) >= 4] - 4
        # Seal the 4 gaps
        new_indices = np.array([
                [22,23,24],
                [25,28,26],
                [27,29,31],
                [30,33,32],
            ],dtype=np.uint16) - 4
        indices = np.concatenate([indices, new_indices ])

# Normalize coordinates
coordinates /= norm(coordinates,axis=1)[:,None]

# Minimizations
for n in range(minimizations):
    deltas = np.zeros(coordinates.shape,dtype="float32")
    edge_coordinates = coordinates[edges.flatten()] \
        .reshape((len(edges), 2, 3))
    edge_diffs = edge_coordinates[:,1,:] - edge_coordinates[:,0,:]
    edge_lengths = norm(edge_diffs, axis=1)
    mean_edge = np.mean(edge_lengths)
    edge_delta = (edge_lengths - mean_edge)/mean_edge
    for n in range(len(edges)):
        e1, e2 = edges[n]
        c1, c2 = coordinates[e1], coordinates[e2]
        d = c2 - c1
        edelta = edge_delta[n]
        offset = 0.2 * edelta * d
        deltas[e1] += offset
        deltas[e2] -= offset
    coordinates += deltas
    coordinates /= norm(coordinates,axis=1)[:,None]

# Normals
normals = coordinates #identical in a sphere

# Beyond here, the code is no longer specific to spheres

# Calculate triangle coordinates and normals
triangle_indices = indices.flatten()
c = triangle_coordinates = coordinates[triangle_indices] \
    .reshape(indices.shape+(3,))
v1 = c[:,1] - c[:,0]
v1 /= norm(v1,axis=1)[:,None]
v2 = c[:,2] - c[:,0]
v2 /= norm(v2,axis=1)[:,None]
triangle_normals = np.cross(v1, v2)
#FIX: sphere subdivision+minimization ometimes leads to strange triangles with wrong normals
#The following sets the correct normal for a sphere
triangle_normals = np.sum(c, axis=1)/3
#/FIX
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

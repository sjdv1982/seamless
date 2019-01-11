#ported from http://www.opengl-tutorial.org/intermediate-tutorials/tutorial-13-normal-mapping/

import numpy as np
tris = indices.reshape(-1, 3)
tangents = np.zeros((len(uv), 2, 3),dtype=np.float32)
tri_pos = np.zeros( shape=(len(tris), 3, 3), dtype=positions.dtype)
tri_normals = np.zeros( shape=(len(tris), 3, 3), dtype=normals.dtype)
tri_uv = np.zeros( shape=(len(tris), 3, 2), dtype=uv.dtype)
for n in range(3):
    tri_pos[:,n,:] =  np.take(positions, tris[:,n], axis=0)
    tri_normals[:,n,:] =  np.take(normals, tris[:,n], axis=0)
    tri_uv[:,n,:] =  np.take(uv, tris[:,n], axis=0)

deltaPos1 = tri_pos[:,1] - tri_pos[:,0]
deltaPos2 = tri_pos[:,2] - tri_pos[:,0]
deltaUV1 = tri_uv[:,1] - tri_uv[:,0]
deltaUV2 = tri_uv[:,2] - tri_uv[:,0]
r = 1.0 / (np.cross(deltaUV1, deltaUV2) + 1e-12)
tangent = (deltaPos1 * deltaUV2[:,1,None] - deltaPos2 * deltaUV1[:,1,None]) * r[:,None]
#bitangent = (deltaPos2 * deltaUV1[:,0,None] - deltaPos1 * deltaUV2[:,0,None]) * r[:,None] #compute from tangent at the end

rep_tangent = np.empty((len(tangent), 3, 3))
for n in range(3):
    rep_tangent[:,n,:] = tangent
tangent_pre = rep_tangent.reshape(3*len(tangent), 3)
all_normals = tri_normals.reshape(3*len(tri_normals), 3)
all_normals = all_normals/np.linalg.norm(all_normals,axis=1)[:,None]
tangent = tangent_pre - all_normals * np.sum(tangent_pre* all_normals, axis=-1)[:,None]
nonplanar = np.sum(tangent*all_normals,axis=-1)**2
bad = (nonplanar>0.1)
tangent[bad] = np.cross(all_normals[bad], (1,0,0))
#norm_tangent = tangent/np.linalg.norm(tangent,axis=1)[:,None]
bitangent = np.cross(tangent, all_normals)

t, b = tangents[:,0], tangents[:,1]
np.add.at(t, indices, tangent)
#t[indices] = tangent ###
t /= np.linalg.norm(t,axis=1)[:,None]
b[:] = np.cross(t, normals)
return tangents

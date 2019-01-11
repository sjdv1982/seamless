ctx.graph = {}
ctx.graph.interactions = []
ctx.graph.interactions[0] = [[1,2, 5], [3,4, 0], [4,5,6]]
ctx.graph.interactions[0].schema.type = "shapedarray"
ctx.graph.interactions[0].schema.shape = (None, 2)
ctx.graph.interactions[0] = np.zeros((10,2),dtype=np.int32)
ctx.graph.interactions.schema.infer_new_item = "uniform"
ctx.graph.interactions[1] = np.zeros((10,2),dtype=np.int32)
ctx.graph.poses = []
ctx.graph.poses.schema.infer_new_item = "uniform"
ctx.graph.poses.schema.form = "binary"
ctx.graph.poses[0] = np.zeros((100), dtype=np.int32)
ctx.graph.validation.append(
"""
assert len(interactions) == len(poses) - 1
for n in range(len(interactions)):
    pre = interactions[n][:, 0]
    post = interactions[n][:, 1]
    assert np.min(pre) >= 0
    assert np.max(pre) < len(poses[n])
    assert np.min(post) >= 0
    assert np.max(post) < len(poses[n+1])

"""
)
ctx.graph.poses.schema.shape = ()

t = ctx.map_connections = seamless.transformer()
t.interactions = ctx.graph.interactions
t.poses = ctx.graph.poses
ctx.mapped_poses = t
t.code = """
for interaction in interactions:
    poses[...]
return mapped_poses
"""

NSAMPLES=10000000

import seamless
seamless.delegate(level=3)

from seamless import transformer
from seamless.workflow.core.cache.buffer_cache import buffer_cache

def gen_random_rotations(n):
    import numpy as np
    from scipy.spatial.transform import Rotation
    np.random.seed(0)
    return Rotation.random(n).as_matrix()

func = transformer(gen_random_rotations, return_transformation=True)
func.scratch = True
tf = func(NSAMPLES)
tf.compute()
cs = tf.checksum
print(cs)
if cs.value is not None:
    cs2 = cs.bytes()
    assert cs2 not in buffer_cache.buffer_refcount
    buffer_cache._uncache_buffer(cs2)
    assert cs2 not in buffer_cache.buffer_cache

func = transformer(gen_random_rotations)
func.scratch = True
data=func(NSAMPLES)
print("Data type:", type(data))
print("Data shape:",data.shape)
print("Data byte size:", data.nbytes)

func = transformer(gen_random_rotations, return_transformation=True)
func.scratch = True
tf = func(NSAMPLES)
tf.compute()
cs = tf.checksum
print(cs)
if cs.value is not None:
    cs2 = cs.bytes()
    assert cs2 not in buffer_cache.buffer_refcount
    buffer_cache._uncache_buffer(cs2)
    assert cs2 not in buffer_cache.buffer_cache
data = tf.value
print("Data type:", type(data))
print("Data shape:",data.shape)
print("Data byte size:", data.nbytes)

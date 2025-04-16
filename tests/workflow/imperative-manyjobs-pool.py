import asyncio
import sys
import seamless
from seamless import transformer
from seamless.multi import TransformationPool
import numpy as np
import tqdm


def calc_pi(seed, ndots):
    import numpy as np

    np.random.seed(seed)
    CHUNKSIZE = 1000000
    in_circle = 0
    for n in range(0, ndots, CHUNKSIZE):
        nndots = min(n + CHUNKSIZE, ndots) - n
        x = 2 * np.random.rand(nndots) - 1
        y = 2 * np.random.rand(nndots) - 1
        dis = x**2 + y**2
        in_circle += (dis <= 1).sum()
    frac = in_circle / ndots
    pi = 4 * frac
    return pi


calc_pi_remote = transformer(calc_pi, return_transformation=True)

seamless.delegate(level=3, raise_exceptions=True)

np.random.seed(0)
ntrials = 1000
if len(sys.argv) > 1:
    ntrials = int(sys.argv[1])
ndots = 1000000000
if len(sys.argv) > 2:
    ndots = int(sys.argv[2])
poolsize = 10
if len(sys.argv) > 3:
    poolsize = int(sys.argv[3])

seeds = np.random.randint(0, 999999, ntrials)

pool = TransformationPool(poolsize)
with tqdm.trange(0, ntrials) as progress:
    transformations = pool.apply(
        lambda n: calc_pi_remote(seeds[n], ndots),
        ntrials,
        callback=lambda *args: progress.update(),
    )
# results = [tf.value for tf in transformations]
fut = asyncio.gather(*[tf.get_value() for tf in transformations])
results = asyncio.get_event_loop().run_until_complete(fut)

results = np.array(results)
print(results.mean(), results.std(), np.pi)

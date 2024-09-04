import sys
import seamless
from seamless import transformer


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

seamless.delegate()

import numpy as np

np.random.seed(0)
ntrials = 1000
ndots = 1000000000
seeds = np.random.randint(0, 999999, ntrials)
transformations = [calc_pi_remote(seed, ndots) for seed in seeds]
for tfnr, tf in enumerate(transformations):
    tf.start()

import asyncio


async def main():
    print("Get status")
    while 1:
        statuses, counts = np.unique(
            [tf.status for tf in transformations], return_counts=True
        )
        print(list(zip(statuses, counts)))
        if "Status: pending" not in statuses and "Status: running" not in statuses:
            break
        await asyncio.sleep(3)


asyncio.get_event_loop().run_until_complete(main())

has_exceptions = False
for t, tf in enumerate(transformations):
    if tf.status.find("exception") > -1:
        print(tf.exception)
        has_exceptions = True

if not has_exceptions:
    results = [tf.value for tf in transformations]
    results = np.array(results)
    print(results.mean(), results.std(), np.pi)

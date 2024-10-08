@transformer(return_transformation=True)
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


transformations = [calc_pi(seed, ndots) for seed in seeds]
for tf in transformations:
    tf.start()

result = 0
for tf in transformations:
    tf.compute()
    result += tf.value
result /= len(seeds)
RESULT = result

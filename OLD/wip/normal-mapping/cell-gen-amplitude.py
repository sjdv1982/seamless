import numpy as np
from scipy.ndimage.filters import gaussian_filter
sigma = 5
np.random.seed(12)
a = 2* np.random.normal(size=(200, 200, 3))
for n in range(3):
    a[:,:,n] = gaussian_filter(a[:,:,n], sigma=sigma, mode="wrap")
a = np.maximum(a, -1)
a = np.minimum(a, 1)
a-= a.mean(axis=0).mean(axis=0)
a /= a.std(axis=0).std(axis=0)
a[:,:,0] *= 0.004
result =  (a/2+0.5).astype(np.float32)
return result

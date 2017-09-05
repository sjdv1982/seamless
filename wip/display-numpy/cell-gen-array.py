import numpy as np
from scipy.ndimage.filters import gaussian_filter
sigma = 1
np.random.seed(0)
a = np.random.normal(size=(100, 200, 3))
for n in range(3):
    a[:,:,n] = gaussian_filter(a[:,:,n], sigma=sigma)
return a[:,:,0]

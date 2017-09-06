import numpy as np
from scipy.ndimage.filters import gaussian_filter
sigma = 1
np.random.seed(0)
a = np.random.normal(size=(100, 200, 3))
for n in range(3):
    a[:,:,n] = gaussian_filter(a[:,:,n], sigma=sigma, mode="wrap")
ret = np.zeros((100, 200))
ret0 = a[:,:,0]
ret[:50,:100] = ret0[50:,100:]
ret[50:,:100] = ret0[:50,100:]
ret[:50,100:] = ret0[50:,:100]
ret[50:,100:] = ret0[:50,:100]
return ret
#return a[:,:,0]

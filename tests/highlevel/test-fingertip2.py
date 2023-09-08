import time

from seamless import transformer
import seamless
seamless.config.delegate(level=3)
    
@transformer    
def func(a,b):
    return 201 * a + 7 * b

t = time.time()
print(func(4,8))
print("{:.1f} seconds elapsed".format(time.time()-t))
import time

from seamless import transformer
import seamless
if seamless.delegate(level=3):
    seamless.delegate(level=0)
    
@transformer    
def func(a,b):
    import time
    time.sleep(3)
    return 201 * a + 7 * b

t = time.time()
print(func(4,8))
print("{:.1f} seconds elapsed".format(time.time()-t))
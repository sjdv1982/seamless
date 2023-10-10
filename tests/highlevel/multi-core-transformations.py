import os
import random
import time
import seamless
import asyncio
    
if "DELEGATE" in os.environ:
    seamless.config.delegate()
else:
    seamless.config.delegate(False)
    seamless.config.set_ncores(5)

from seamless import transformer

random.seed(time.time())


@transformer(return_transformation=True)
def func(jobid, sleep, rand):
    print("Run job", jobid)
    import time
    time.sleep(sleep)
    return jobid

func.direct_print = True

loop = asyncio.get_event_loop()

tf = func(1, 5, random.random())
tf.meta = {"ncores": 5}
t1 = tf.task()

t = time.time()
loop.run_until_complete(asyncio.sleep(0.5))

tf2 = func(2, 2, random.random())
tf2.meta = {"ncores": 1}
t2 = tf2.task()

loop.run_until_complete(t2)
print("{:.1f} seconds elapsed".format(time.time() - t))

print("Job 1", tf.status, tf.value, tf.exception)
print("Job 2", tf2.status, tf2.value, tf2.exception)
print("START")
import os
import seamless
import time
import asyncio

from seamless.core.transformation import get_global_info
get_global_info()
    
if "DELEGATE" in os.environ:
    seamless.config.delegate()
else:
    seamless.config.delegate(False)
    
from seamless import transformer

@transformer(return_transformation=True)
def func(a, delay):
    import time
    time.sleep(delay)
    return 10 * a


async def main():
    start_time = time.time()
    task1 = func(a=1, delay=1).task()
    task2 = func(a=2, delay=1).task()
    task3 = func(a=3, delay=1).task()
    task4 = func(a=4, delay=2).task()
    result = await task1
    print(result)
    result = await task2
    print(result)
    result = await task3
    print(result)
    result = await task4
    print(result)
    t = time.time() - start_time
    print("Time to complete: {:.1f} seconds".format(t))

if not asyncio.get_event_loop().is_running():
    asyncio.get_event_loop().run_until_complete(main())
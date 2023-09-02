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
    seamless.config.delegate(level=0)
    
from seamless.imperative import transformer_async

@transformer_async
def func(a, delay):
    import time
    time.sleep(delay)
    return 10 * a


async def main():
    start_time = time.time()
    coro1 = func(a=1, delay=1)
    fut1 = asyncio.ensure_future(coro1)
    coro2 = func(a=2, delay=1)
    fut2 = asyncio.ensure_future(coro2)
    coro3 = func(a=3, delay=1)
    fut3 = asyncio.ensure_future(coro3)
    coro4 = func(a=4, delay=2)
    fut4 = asyncio.ensure_future(coro4)
    result = await fut1
    print(result)
    result = await fut2
    print(result)
    result = await fut3
    print(result)
    result = await fut4
    print(result)
    t = time.time() - start_time
    print("Time to complete: {:.1f} seconds".format(t))

if not asyncio.get_event_loop().is_running():
    asyncio.get_event_loop().run_until_complete(main())
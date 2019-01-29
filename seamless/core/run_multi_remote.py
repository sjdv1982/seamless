"""Run multiple remote servers, return the first value
"""

import asyncio

async def run_multi_remote(serverlist, *args, **kwargs):
    if not len(serverlist):
        return None
    futures = []
    for func in serverlist:
        coro = func(*args, **kwargs)
        future = asyncio.ensure_future(coro)
        futures.append(future)
    try:
        while 1:
            if not len(futures):
                return None
            done, pending = asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
            for future in done:
                if not future.cancelled() and not future.exception():
                    result = future.result()
                    if result is not None:
                        return result            
            futures = pending
    except asyncio.CancelledError:
        for future in futures:
            if not future.done():
                future.cancel()

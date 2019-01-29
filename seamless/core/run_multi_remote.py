"""Run multiple remote servers, return the first value
"""

import asyncio
import sys
import traceback

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
            done, pending = await asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
            for future in done:
                exception = future.exception()
                if not future.cancelled() and not exception:
                    result = future.result()
                    if result is not None:
                        for pending_future in pending:
                            pending_future.cancel()
                        return result 
                elif exception:
                    exc = traceback.format_exception(type(exception), exception, exception.__traceback__)
                    exc = "".join(exc)
                    print("run_multi_remote", exc, file=sys.stderr)
            futures = pending
    except asyncio.CancelledError:
        for future in futures:
            if not future.done():
                future.cancel()

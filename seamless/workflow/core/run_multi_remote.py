"""Run multiple remote servers, return the first value
"""

import asyncio
import sys
import traceback


async def run_multi_remote(serverlist, *args, **kwargs):
    # print("run_multi_remote", len(serverlist))
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
            done, pending = await asyncio.wait(
                futures, return_when=asyncio.FIRST_COMPLETED
            )
            for future in done:
                exception = future.exception()
                if not future.cancelled() and not exception:
                    result = future.result()
                    if result is not None:
                        for pending_future in pending:
                            pending_future.cancel()
                        return result
                elif exception:
                    exc = traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                    exc = "".join(exc)
                    print("run_multi_remote", exc, file=sys.stderr)
            futures = pending
    except asyncio.CancelledError:
        for future in futures:
            if not future.done():
                future.cancel()


async def run_multi_remote_pair(serverlist, *args, **kwargs):
    """Each server is a pair (p1,p2) of functions; for the first server where p1 returns True, p2 is invoked"""
    if not len(serverlist):
        return None
    futures = []
    serverlist = list(serverlist)
    for servernr, server in enumerate(serverlist):
        func = server[0]
        coro = func(*args, **kwargs)
        future = asyncio.ensure_future(coro)
        futures.append((servernr, future))
    try:
        result = None
        while 1:
            if not len(futures):
                return None
            futures2 = [ff[1] for ff in futures]
            await asyncio.wait(futures2, return_when=asyncio.FIRST_COMPLETED)
            pending = []
            for servernr, future in futures:
                if not future.done():
                    pending.append((servernr, future))
                exception = future.exception()
                if not future.cancelled() and not exception:
                    result = future.result()
                    if result is not None:
                        for pending_future in pending:
                            pending_future.cancel()
                        result_servernr = servernr
                        break
                elif exception:
                    exc = traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                    exc = "".join(exc)
                    print("run_multi_remote_pair stage 1", exc, file=sys.stderr)
            if result == True:
                break
            futures = pending
    except asyncio.CancelledError:
        for servernr, future in enumerate(futures):
            if not future.done():
                future.cancel()
    sequel_func = serverlist[result_servernr][1]
    try:
        coro = sequel_func(*args, **kwargs)
        future = asyncio.ensure_future(coro)
        await future
        exception = future.exception()
        if exception:
            exc = traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
            exc = "".join(exc)
            print("run_multi_remote_pair stage 2", exc, file=sys.stderr)
        else:
            result = future.result()
        return result
    except asyncio.CancelledError:
        future.cancel()

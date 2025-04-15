import threading
import json
from json import JSONDecodeError
import sys
import weakref
import asyncio
import atexit

import aiohttp
from aiohttp import ClientConnectionError

from seamless import Checksum, Buffer
from seamless.util import unchecksum
from seamless.checksum import Expression
from seamless.checksum.buffer_info import BufferInfo

from seamless import Buffer, Checksum

sessions_async = weakref.WeakKeyDictionary()


async def has(url: str, checksum: Checksum) -> bool:
    """Check if a buffer is available at a remote URL.
    URL is accessed using HTTP GET, with /has added to the URL,
     and the checksum as parameter"""

    thread = threading.current_thread()
    session_async = sessions_async.get(thread)
    if session_async is not None:
        try:
            loop = asyncio.get_running_loop()
            if loop != session_async._loop:
                session_async = None
        except RuntimeError:  # no event loop running:
            pass
    if session_async is None:
        timeout = aiohttp.ClientTimeout(total=10)
        session_async = aiohttp.ClientSession(timeout=timeout)
        sessions_async[thread] = session_async

    checksum = Checksum(checksum)
    assert checksum
    cs = unchecksum(checksum)
    csbuf = json.dumps(cs)

    try:
        path = url + "/has"

        async with session_async.get(path, data=csbuf) as response:
            if int(response.status / 100) in (4, 5):
                raise ClientConnectionError()
            result0 = await response.read()
            result = json.loads(result0)
        if not isinstance(result, list) or len(result) != 1:
            raise ValueError(result)
        if not isinstance(result[0], bool):
            raise ValueError(result)
        return result[0]
    except (ClientConnectionError, JSONDecodeError):
        # import traceback; traceback.print_exc()
        return
    except Exception:
        import traceback

        traceback.print_exc()
        return


async def get(url: str, checksum: Checksum) -> bytes | None:
    """Download a buffer from a remote URL.
    URL is accessed using HTTP GET, with /<checksum> added to the URL"""

    thread = threading.current_thread()
    session_async = sessions_async.get(thread)
    if session_async is not None:
        try:
            loop = asyncio.get_running_loop()
            if loop != session_async._loop:
                session_async = None
        except RuntimeError:  # no event loop running:
            pass
    if session_async is None:
        timeout = aiohttp.ClientTimeout(total=10)
        session_async = aiohttp.ClientSession(timeout=timeout)
        sessions_async[thread] = session_async

    checksum = Checksum(checksum)
    assert checksum

    curr_buf_checksum = None
    while 1:
        try:
            path = url + "/" + str(checksum)
            async with session_async.get(path) as response:
                if int(response.status / 100) in (4, 5):
                    raise ClientConnectionError()
                buf = await response.read()
            buf_checksum = Buffer(buf).get_checksum().value
            if buf_checksum != checksum:
                if buf_checksum != curr_buf_checksum:
                    curr_buf_checksum = buf_checksum
                    continue
                print(
                    "WARNING: '{}' has the wrong checksum for {}".format(url, checksum),
                    file=sys.stderr,
                )
                return
            break
        except ClientConnectionError:
            # import traceback; traceback.print_exc()
            return
        except Exception:
            import traceback

            traceback.print_exc()
            return

    return buf


def _close_async_sessions():
    for session_async in sessions_async.values():
        asyncio.ensure_future(session_async.close())


atexit.register(_close_async_sessions)

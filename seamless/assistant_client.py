"""Client to interact with the Seamless assistant"""

import asyncio
import os
import aiohttp
from aiohttp.client_exceptions import ServerDisconnectedError

from seamless import Buffer, Checksum


async def run_job(
    checksum: Checksum, tf_dunder, *, fingertip: bool, scratch: bool
) -> Checksum:
    """Runs a transformation job via the Seamless assistant"""
    from seamless.checksum.buffer_cache import buffer_cache
    from seamless.config import get_assistant, InProcessAssistant

    timeout = os.environ.get("SEAMLESS_ASSISTANT_JOB_TIMEOUT", None)
    if timeout is not None:
        timeout = float(timeout)
    checksum = Checksum(checksum)
    assistant = get_assistant()
    if assistant is None:
        return None
    if isinstance(assistant, InProcessAssistant):
        result = await assistant.run_job(
            checksum, tf_dunder, fingertip=fingertip, scratch=scratch
        )
        result = Checksum(result).hex()
        return result

    # One session per request is really bad... but what can we do?
    async with aiohttp.ClientSession() as session:
        data = {
            "checksum": Checksum(checksum).hex(),
            "dunder": tf_dunder,
            "scratch": scratch,
            "fingertip": fingertip,
        }
        for _retry in range(5):
            try:
                while 1:
                    async with session.put(
                        assistant, json=data, timeout=timeout
                    ) as response:
                        content = await response.read()
                        if response.status == 202:
                            await asyncio.sleep(0.1)
                            continue
                        if not (scratch and fingertip):
                            try:
                                content = content.decode()
                            except UnicodeDecodeError:
                                pass
                        if response.status != 200:
                            msg1 = f"Error {response.status} from assistant:"
                            if isinstance(content, bytes):
                                msg1 = msg1.encode()
                            err = msg1 + content
                            try:
                                if isinstance(err, bytes):
                                    err = err.decode()
                            except UnicodeDecodeError:
                                pass
                            raise RuntimeError(err)
                        break
                break
            except ServerDisconnectedError:
                continue

    if scratch and fingertip:
        result_buffer = content
        result_checksum = Buffer(result_buffer).get_checksum()
        buffer_cache.cache_buffer(result_checksum, result_buffer)
    else:
        result_checksum = Checksum(content)
    return result_checksum

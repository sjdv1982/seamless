import asyncio
import aiohttp
import os
#session = aiohttp.ClientSession()
from aiohttp.client_exceptions import ServerDisconnectedError
    
async def run_job(checksum, tf_dunder, *, fingertip, scratch):
    from seamless.highlevel import Checksum
    from . import parse_checksum
    from seamless import calculate_checksum
    from seamless.core.cache.buffer_cache import buffer_cache
    from .config import get_assistant, InProcessAssistant

    timeout = os.environ.get("SEAMLESS_ASSISTANT_JOB_TIMEOUT", None)
    if timeout is not None:
        timeout = float(timeout)
    checksum = parse_checksum(checksum)
    assistant = get_assistant()
    if assistant is None:
        return None
    if isinstance(assistant, InProcessAssistant):
        result = await assistant.run_job(checksum, tf_dunder)
        result = Checksum(result).hex()
        return result

    # One session per request is really bad... but what can we do?
    async with aiohttp.ClientSession() as session:        
        data={"checksum":checksum, "dunder":tf_dunder, "scratch": scratch, "fingertip": fingertip}
        for retry in range(5):
            try:
                while 1:
                    async with session.put(assistant, json=data,timeout=timeout) as response:
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
                            msg1 = (f"Error {response.status} from assistant:")
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
        result_checksum = calculate_checksum(result_buffer)
        buffer_cache.cache_buffer(result_checksum, result_buffer)
        result_checksum = result_checksum.hex()
    else:
        result_checksum = parse_checksum(content)
    return result_checksum
    
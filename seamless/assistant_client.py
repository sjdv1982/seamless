import asyncio
import aiohttp
import atexit
#session = aiohttp.ClientSession()
    
async def run_job(checksum):
    from . import parse_checksum
    from .config import get_assistant
    checksum = parse_checksum(checksum)
    assistant = get_assistant()
    if assistant is None:
        return None

    # One session per request is really bad... but what can we do?
    async with aiohttp.ClientSession() as session:
        while 1:
            async with session.put(assistant, data=checksum) as response:
                content = await response.read()
                if response.status == 202:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    content = content.decode()
                except UnicodeDecodeError:
                    pass                
                if response.status != 200:
                    raise RuntimeError(f"Error {response.status} from assistant:" + content)
                break

    result_checksum = parse_checksum(content)
    return result_checksum
    
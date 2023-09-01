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
        async with session.put(assistant, data=checksum) as response:
            content = await response.read()
            try:
                content = content.decode()
            except Exception:
                pass                
            if response.status != 200:
                raise RuntimeError(content)

    '''       
    async with session.put(assistant, data=checksum) as response:
        content = await response.read()
        if response.status != 200:
            raise RuntimeError(content)
    '''
    result_checksum = parse_checksum(content)
    return result_checksum
    
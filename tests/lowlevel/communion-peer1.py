from seamless.core import context
from seamless import communionserver
ctx = context(toplevel=True)

import asyncio
done = asyncio.sleep(7)
asyncio.get_event_loop().run_until_complete(done)

communionserver.send_message("Hello from 1")

done = asyncio.sleep(12)
asyncio.get_event_loop().run_until_complete(done)
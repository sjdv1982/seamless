from seamless.core import context
ctx = context(toplevel=True)

import asyncio
done = asyncio.sleep(12)
asyncio.get_event_loop().run_until_complete(done)
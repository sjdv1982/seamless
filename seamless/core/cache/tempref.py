import time, copy
import asyncio
import bisect
from collections import deque

class TempRefManager:
    def __init__(self):
        self.refs = deque()
        self.running = False

    def add_ref(self, ref, lifetime, on_shutdown):
        expiry_time = time.time() + lifetime
        self.refs.append((expiry_time, ref, on_shutdown))

    def purge_all(self):
        """Purges all refs, regardless of expiry time
        Only call this when Seamless is shutting down"""
        while len(self.refs):
            _, ref, on_shutdown = self.refs.pop()
            if not on_shutdown:
                continue
            try:
                ref()
            except:
                pass

    def purge(self):
        """Purges expired refs"""
        t = time.time()
        pos = bisect.bisect(self.refs, (t, None, None))
        for n in range(pos):
            item = self.refs.popleft()
            _, ref, _ = item
            ref()

    async def loop(self):
        if self.running:
            return
        self.running = True
        while 1:
            try:
                self.purge()
            except Exception:
                import traceback
                traceback.print_exc()
            await asyncio.sleep(0.05)
        self.running = False

temprefmanager = TempRefManager()

coro = temprefmanager.loop()
import asyncio
task = asyncio.ensure_future(coro)

import atexit
atexit.register(lambda  *args, **kwargs: task.cancel())
import time, copy
import asyncio
import bisect
from collections import deque

class TempRefManager:
    def __init__(self):
        self.refs = deque()
        self.running = False

    def add_ref(self, ref, lifetime, on_shutdown, *, group=None):
        expiry_time = time.time() + lifetime
        self.refs.append((expiry_time, ref, on_shutdown, group))

    def purge_all(self):
        """Purges all refs, regardless of expiry time
        Only call this when Seamless is shutting down"""
        while len(self.refs):
            _, ref, on_shutdown, _ = self.refs.popleft()
            if not on_shutdown:
                continue
            try:
                ref()
            except:
                pass

    def purge_group(self, group):
        """Purges all refs belonging to a certain group,
        regardless of expiry time"""
        refs_to_keep = []
        refs_to_purge = []
        while len(self.refs):
            ref = self.refs.popleft()
            if ref[3] == group:
                refs_to_purge.append(ref)
            else:
                refs_to_keep.append(ref)
        for ref in refs_to_keep:
            self.refs.append(ref)
        for _, ref, _, _ in refs_to_purge:
            ref()

    def purge(self):
        """Purges expired refs"""
        t = time.time()
        pos = bisect.bisect(self.refs, (t, None, None))
        for n in range(pos):
            item = self.refs.popleft()
            _, ref, _, _ = item
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
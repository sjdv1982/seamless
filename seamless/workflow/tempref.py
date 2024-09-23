"""Manager for temporary references.
A singleton manager is fired up on import.
This manager runs continuously in a coroutine.
Do not change event loop afterwards!
On shutdown, temporary references are cleaned up.
"""

import time
import asyncio
import bisect
from collections import deque
import atexit
from typing import Callable


class TempRefManager:
    """Manager for temporary references.

    Runs continuously in a coroutine.
    Do not change event loop afterwards"""

    def __init__(self, main_loop_interval: float = 0.05):
        """Main loop will do a purge every main_loop_interval seconds"""
        self.refs = deque()
        self.running = False
        self.main_loop_interval = main_loop_interval

    def add_ref(self, ref: Callable, lifetime: float, on_shutdown: bool, *, group=None):
        """Add reference.
        - ref: object that will be called with zero arguments on expiry
        - lifetime: expiry time
        - on_shutdown: if the ref must be called when Seamless shuts down
        - group: for purge_group
        """
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
            except:  # pylint: disable=bare-except
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
        for _ in range(pos):
            item = self.refs.popleft()
            _, ref, _, _ = item
            ref()

    async def loop(self):
        """Main loop for purging expired refs.
        Does a purge every main_loop_interval seconds"""
        if self.running:
            return
        self.running = True
        while 1:
            try:
                self.purge()
            except Exception:
                import traceback

                traceback.print_exc()
            await asyncio.sleep(self.main_loop_interval)
        self.running = False


temprefmanager = TempRefManager()

coro = temprefmanager.loop()

task = asyncio.ensure_future(coro)

atexit.register(lambda *args, **kwargs: task.cancel())

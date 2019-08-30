import time, copy
import asyncio

class TempRefManager:
    def __init__(self):
        self.refs = []
        self.running = False
    
    def add_ref(self, ref, lifetime):
        expiry_time = time.time() + lifetime
        self.refs.append((ref, expiry_time))

    def purge_all(self):
        """Purges all refs, regardless of expiry time
        Only call this when Seamless is shutting down"""
        while len(self.refs):
            ref, _ = self.refs.pop(0)
            try:
                ref()
            except:
                pass

    def purge(self):
        """Purges expired refs"""
        t = time.time()
        for item in copy.copy(self.refs):
            ref, expiry_time = item
            if expiry_time < t:
                self.refs.remove(item)
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
            await asyncio.sleep(0.001)
        self.running = False

temprefmanager = TempRefManager()

coro = temprefmanager.loop()
import asyncio
asyncio.ensure_future(coro)
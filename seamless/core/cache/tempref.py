import time, copy
import asyncio

class TempRefManager:
    def __init__(self):
        self.refs = set()
        self.running = False
    
    def add_ref(self, ref, lifetime):
        expiry_time = time.time() + lifetime
        self.refs.add((ref, expiry_time))

    def purge(self):
        """Purges expired refs"""
        t = time.time()
        for item in copy.copy(self.refs):
            ref, expiry_time = item
            if expiry_time < t:
                self.refs.remove(item)
                if callable(ref):
                    ref() 

    async def loop(self):
        if self.running:
            return
        self.running = True
        while 1:
            try:
                self.purge()
            except:
                import traceback
                traceback.print_exc()
            await asyncio.sleep(0.1)
        self.running = False

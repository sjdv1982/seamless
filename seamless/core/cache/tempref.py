import time, copy

class TempRefManager:
    def __init__(self):
        self.refs = set()
    
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

"""Defines a dummy server that does transformations and gives back preliminary and progress results
After 3 secs, the server gets hard-canceled, then the exception gets cleared, and execution restarts
"""

import asyncio
import seamless
import json
from seamless.core import context, cell, transformer, macro_mode_on
from seamless import get_hash

def h(value):
    return get_hash(json.dumps(value)+"\n")

seamless.set_ncores(0)

class DummyClient:
    def __init__(self):
        self.st = 1
        self.progress = 0
        self.prelim = None
        self.job = None
        self.queue = asyncio.Queue()
    async def _server(self):
        print("Server")
        for n in range(10):
            await asyncio.sleep(1)
            self.progress = 10 * (n+1)
            prelim = 0.1 * (n+1)
            self.prelim = h(prelim)
            await self.queue.put(None)
        self.st = 3        
        self.result = h(1.0)        
        await self.queue.put(None)
    async def submit(self, checksum):
        self.checksum = checksum
        self.job = asyncio.ensure_future(self._server())
        self.st = 2
    async def wait(self, checksum):
        await self.queue.get()
        while 1:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
    async def hard_cancel(self, checksum):
        print("Server CANCEL")
        self.job.cancel()
        self.st = 1
        self.progress = 0
        self.prelim = None
    async def clear_exception(self, checksum):
        pass # dummy
    async def status(self, checksum):
        if self.st == 2:
            return self.st, self.progress, self.prelim
        elif self.st == 3:
            return self.st, self.result
        else:
            return self.st, None

from seamless.communion_client import communion_client_manager
m = communion_client_manager
m.clients["transformation"] = [
    DummyClient(),
] # dirty hack

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(2)
    ctx.cell2 = cell().set(3)
    ctx.code = cell("python").set("c = a + b")
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.tf.c.connect(ctx.result)
    ctx.code.connect(ctx.tf.code)
    ctx.hashcell = cell()

for n in range(10):
    ctx.hashcell.set(0.1 * (n+1) )
    ctx.compute(0.05)

def report():
    print(ctx.tf.status, ", exception:", ctx.tf.exception)
    print(ctx.tf.value)
    print(ctx.result.status)
    print(ctx.result.value)
    print()

for n in range(5):
    print("STEP", n+1)
    report()
    ctx.compute(0.5)

ctx.tf.cancel()
ctx.compute(0.1)
report()
ctx.tf.clear_exception()

for n in range(25):
    print("STEP", n+1)
    report()
    ctx.compute(0.5)

ctx.compute()

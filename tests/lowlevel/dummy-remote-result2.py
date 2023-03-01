"""Define three servers that can perform dummy remote execution for transformer results
The first one cannot do the job (should never be called)
The second one pretends to be running, but then gives a negative status
The third one does the job
"""

import asyncio
import seamless
import json
from seamless.core import context, cell, transformer, macro_mode_on
from seamless import calculate_checksum

def h(value):
    return calculate_checksum(json.dumps(value)+"\n")

seamless.set_ncores(0)

class DummyClient0:
    async def status(self, checksum, meta):
        return -1, None

class DummyClient1:
    def __init__(self):
        self.st = 2
        self.progress = 0
        self.prelim = None
    async def submit(self, checksum, meta):
        raise Exception
    async def wait(self, checksum):
        pass
    async def status(self, checksum, meta):
        print("Server 1 status", self.st)
        if self.st == 2:
            self.st = -1
            return 2, self.progress, self.prelim
        elif self.st == 3:
            return self.st, self.result
        else:
            return self.st, None

class DummyClient2:
    def __init__(self):
        self.st = 1
        self.progress = 0
        self.prelim = None
        self.job = None
    async def _server(self):
        print("Server 2")
        await asyncio.sleep(2)
        self.result = h(42)
        self.st = 3
    async def submit(self, checksum, meta):
        self.checksum = checksum
        self.job = asyncio.ensure_future(self._server())
        self.st = 2
    async def wait(self, checksum):
        assert self.job is not None
        await self.job
    async def status(self, checksum, meta):
        if self.st == 2:
            return self.st, self.progress, self.prelim
        elif self.st == 3:
            return self.st, self.result
        else:
            return self.st, None

from seamless.communion_client import communion_client_manager
m = communion_client_manager
m.clients["transformation"] = [
    DummyClient0(),
    DummyClient1(),
    DummyClient2(),
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
    
ctx.hashcell.set(42)
ctx.compute(0.1)
ctx.hashcell.set(43)
ctx.compute(0.1)
ctx.hashcell.set(99)
ctx.compute(0.1)

ctx.compute()
print(ctx.status)
print(ctx.tf.exception)
print(ctx.result.value)
print("STOP")
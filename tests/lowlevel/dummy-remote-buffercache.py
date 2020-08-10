"""Define three servers that can perform dummy remote caching for transformer results
The first one returns None; status should indicate that buffer is not available
The second one raises an Exception; status should indicate that the buffer is remote
The third one gives the correct result after 0.5 second
"""

import asyncio
import seamless
import json
from seamless.core import context, cell, transformer, macro_mode_on

cache = {}

async def server1(checksum):
    print("Server 1")
    return None

async def server2(checksum):
    print("Server 2...")
    print("... server 2")
    raise Exception # Server 2 raises an exception

async def server3(checksum):
    print("Server 3...")
    await asyncio.sleep(0.5)
    print("... server 3")
    return cache.get(checksum)

seamless.set_ncores(0)

class DummyClient:
    def get_peer_id(self):
        return id(self)
    async def status(self, checksum):
        return self.st
    def __init__(self, func, st):
        self.st = st
        self.submit = func

from seamless.communion_client import communion_client_manager
m = communion_client_manager
m.clients["buffer"] = [DummyClient(s, st)
    for s,st in ((server1, -2), (server2, 0), (server3, 1))
]

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.cell3 = cell().set(3)

ctx.compute()

from seamless.core.cache.buffer_cache import buffer_cache
from seamless.core.protocol.calculate_checksum import checksum_cache

# Comment out the next line to get a cache miss
cache.update(buffer_cache.buffer_cache.copy())

ctx.destroy()

for k,v in cache.items():
    print(v, k.hex())

buffer_cache.buffer_cache.clear()
checksum_cache.clear()


c1 = "bc4bb29ce739b5d97007946aa4fdb987012c647b506732f11653c5059631cd3d"
c2 = "191fb5fc4a9bf2ded9a09a0a2c4eb3eb90f15ee96deb1eec1a970df0a79d09ba"
c3 = "a3b9a39c707177f10d440c071303df8beff535c40c7c25e92da187b14aac127e"
ctx = context(toplevel=True)
ctx.cell1 = cell().set_checksum(c1)
ctx.cell2 = cell().set_checksum(c2)
ctx.cell3 = cell().set_checksum(c3)
print(ctx.cell1.value)
print(ctx.cell2.value)
print(ctx.cell3.value)
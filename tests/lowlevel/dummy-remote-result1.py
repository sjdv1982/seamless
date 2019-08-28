"""Define four servers that can perform dummy remote caching for transformer results
The first one returns first, but returns -1 (cache miss)
The second one raises an Exception after 2 secs
The third one returns 42 after 3 seconds
The fourth one returns 43 after 5 seconds, i.e. it should be canceled
"""

import asyncio
import seamless
import json
from seamless.core import context, cell, transformer, macro_mode_on
from seamless import get_hash

def h(value):
    return get_hash(json.dumps(value)+"\n")

async def server1(checksum):
    print("Server 1")
    return -3, None

async def server2(checksum):
    print("Server 2...")
    await asyncio.sleep(2)
    print("... server 2")
    raise Exception # Server 2 raises an exception
    
async def server3(checksum):
    print("Server 3...")
    await asyncio.sleep(3)
    print("... server 3")
    return 3, h(42)

async def server4(checksum):
    print("Server 4...")
    try:
        await asyncio.sleep(5)
        print("... server 4")
        return 3, h(43)
    except asyncio.CancelledError:
        print("... server 4 CANCELLED")
        raise

seamless.set_ncores(0)

class DummyClient:
    def __init__(self, func):
        self.status = func


from seamless.communion_client import communion_client_manager
m = communion_client_manager
m.clients["transformation"] = [DummyClient(s) 
    for s in (server1, server2, server3, server4)
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
ctx.equilibrate(0.1)
ctx.hashcell.set(43)
ctx.equilibrate(0.1)
ctx.hashcell.set(99)
ctx.equilibrate(0.1)

ctx.equilibrate()
print(ctx.status)
print(ctx.result.value)
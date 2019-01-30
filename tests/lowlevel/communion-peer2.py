from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell()

import asyncio
done = asyncio.sleep(0.5)
asyncio.get_event_loop().run_until_complete(done)

print("peer2...")
ctx.cell1.from_label("Test label")
print("Peer 2", ctx.cell1.checksum)

print("END peer2")
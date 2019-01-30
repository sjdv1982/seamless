from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set("Test string")
    ctx.cell1.set_label("Test label")

print("Peer 1", ctx.cell1.checksum)

import asyncio
#done = asyncio.sleep()
#asyncio.get_event_loop().run_until_complete(done)
asyncio.get_event_loop().run_forever()

print("END peer1")
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, unilink
from seamless import calculate_checksum

from seamless import communion_server
communion_server.configure_servant(
    buffer=True,
    buffer_status=True,
    transformation_job=True,
    transformation_status=True,
)
communion_server.start()

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(2)
    ctx.cell2 = cell().set(3)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer").set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

ctx.compute()
print("Secret source code ", ctx.code.checksum)
print("hash verification  ", calculate_checksum("c = a + b\n").hex())
print(ctx.result.value)
print(ctx.result.checksum)
print("Communion peer 1 ready.")

import sys
if len(sys.argv) == 1 or sys.argv[1] != "--interactive":
    import asyncio
    asyncio.get_event_loop().run_forever()
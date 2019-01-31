import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link
from seamless import get_hash

seamless.set_ncores(0)
from seamless import communionserver
communionserver.configure_master(transformer_result=True)

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
    ctx.code = pytransformercell()    
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

import asyncio
done = asyncio.sleep(1)
ctx.equilibrate()
asyncio.get_event_loop().run_until_complete(done)

ctx.code.from_label("Secret source code")
print("Secret source code", ctx.code.checksum)
#print(ctx.code.value) ###

ctx.equilibrate()
print(ctx.status)

print(ctx.result.value)

communionserver.configure_master(value=False)
print(ctx.code.value) # Should raise Exception

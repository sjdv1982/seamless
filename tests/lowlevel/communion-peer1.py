from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link
from seamless import get_hash

from seamless import communionserver
communionserver.configure_master(value=True, transformer_result=True)
communionserver.configure_servant(value=True, transformer_job=True)

import seamless
redis_sink = seamless.RedisSink()
redis_cache = seamless.RedisCache()


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
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.set_label("Secret source code")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

ctx.equilibrate()
print("Secret source code ", ctx.code.checksum, ctx._manager.value_get(bytes.fromhex(ctx.code.checksum)))
print("hash verification  ", get_hash("c = a + b\n").hex())
print(ctx.result.checksum)

import asyncio
asyncio.get_event_loop().run_forever()
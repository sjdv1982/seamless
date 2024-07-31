import json
import seamless
seamless.delegate(False)

from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer,  StructuredCell
import os
os.makedirs("/tmp/mount-test", exist_ok=True)
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.a = cell("plain").set({"x": 2})
    ctx.b = cell("plain").set(2)
    ctx.b.mount("/tmp/mount-test/b.json", authority="cell")
    ctx.a.connect(ctx.tf.a)
    ctx.b.connect(ctx.tf.b)
    ctx.code = cell("transformer").set("a['x'] + b")
    ctx.code.connect(ctx.tf.code)
    ctx.c = cell("plain")
    ctx.tf.c.connect(ctx.c)

ctx.compute()

import asyncio
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.5))
with open("/tmp/mount-test/b.json", "w") as f:
    f.write("10\n")
asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.5))
ctx.compute()
print(ctx.b.value)
print(ctx.c.value)

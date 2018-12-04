import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link
from seamless import shareserver

shareserver.start()

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1_link = link(ctx.cell1)
    ctx.cell1_link.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = pytransformercell().set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.result_link = link(ctx.result)
    ctx.tf.c.connect(ctx.result_link)

namespace = shareserver.new_namespace("ctx")
print("OK1")
shareserver.share(namespace, "cell1", ctx.cell1)
ctx.cell1.set(99)
import asyncio
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.sleep(5))
print("OK2")
shareserver.send_update(namespace, "cell1")
print("OK3")

ctx.equilibrate()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.equilibrate()
print(ctx.result.value)
ctx.code.set("c = a + b + 1000")
ctx.equilibrate()
print(ctx.result.value)
print(ctx.status())

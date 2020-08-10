import asyncio, traceback
loop = asyncio.get_event_loop()

import sys
from seamless.core.cache import buffer_cache, CacheMissError
buffer_cache.LIFETIME_TEMP = 0.001
buffer_cache.LIFETIME_TEMP_SMALL = 0.001
from seamless.core.protocol import calculate_checksum_module as calculate_checksum
calculate_checksum.checksum_cache.disable()

from seamless.core import context, cell, transformer
import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

ctx = context(toplevel=True)
manager = ctx._get_manager()

ctx.a = cell("int")
ctx.a.set(10)
ctx.tf = transformer({"a": "input", "aa": "output"})
ctx.tf.code.cell().set("print('RUN', a); aa = 2 * a")
ctx.a.connect(ctx.tf.a)
ctx.aa = cell("int")
ctx.tf.aa.connect(ctx.aa)
ctx.compute()
checksum = ctx.aa.checksum
print(checksum)
print(ctx.aa.value)
ctx.a.set(5)
print("START")
ctx.compute()
loop.run_until_complete(asyncio.sleep(0.1))
ctx.a.set(10)
ctx.compute()

ctx.aa._fingertip_recompute = False

print(ctx.aa.checksum, checksum)
try:
    print(ctx.aa.value)
except CacheMissError as exc:
    traceback.print_exception(type(exc), exc, None)

ctx.aa._fingertip_recompute = None
print(ctx.aa.value)

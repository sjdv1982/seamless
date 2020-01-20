import asyncio, traceback
loop = asyncio.get_event_loop()

import sys
from seamless.core.cache import buffer_cache, CacheMissError
buffer_cache.TEMP_KEEP_ALIVE = 0.001
buffer_cache.TEMP_KEEP_ALIVE_SMALL = 0.001
import seamless.core.protocol.calculate_checksum 
calculate_checksum = sys.modules["seamless.core.protocol.calculate_checksum"]
calculate_checksum.checksum_cache.disable()

from seamless.core import context, cell, transformer

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
print(ctx._get_manager().resolve(checksum), checksum)
ctx.a.set(5)
print("START")
ctx.compute()
loop.run_until_complete(asyncio.sleep(0.01))
ctx.a.set(10)
ctx.compute()

print(ctx.aa.checksum, checksum)
try:
    #print(manager.resolve(checksum))
    print(ctx.aa.value)
except CacheMissError as exc:
    traceback.print_exception(type(exc), exc, None)

loop.run_until_complete(manager.cachemanager.fingertip(checksum))

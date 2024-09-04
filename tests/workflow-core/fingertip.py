import seamless

seamless.delegate(False)

import asyncio, traceback

loop = asyncio.get_event_loop()

import sys
from seamless.workflow.core.cache.buffer_cache import buffer_cache, CacheMissError

buffer_cache.LIFETIME_TEMP = 0.1
buffer_cache.LIFETIME_TEMP_SMALL = 0.1
buffer_cache.LOCAL_MODE_FULL_PERSISTENCE = False
from seamless.workflow.core.protocol import (
    calculate_checksum_module as calculate_checksum,
)

calculate_checksum.checksum_cache.disable()

from seamless.workflow.core import context, cell, transformer

ctx = context(toplevel=True)
manager = ctx._get_manager()

ctx.a = cell("int")
ctx.a.set(10)
ctx.tf = transformer({"a": "input", "aa": "output"})
ctx.tf._scratch = True
ctx.tf._debug = {"direct_print": True}
ctx.tf.code.cell().set("print('RUN', a); aa = 2 * a")
ctx.a.connect(ctx.tf.a)
ctx.aa = cell("int")
ctx.aa._scratch = True
ctx.tf.aa.connect(ctx.aa)
ctx.compute()
checksum = ctx.aa.checksum
print(checksum)
print(ctx.aa.value)
loop.run_until_complete(asyncio.sleep(0.2))

ctx.aa._fingertip_recompute = False

try:
    print(ctx.aa.value)
except CacheMissError as exc:
    traceback.print_exception(type(exc), exc, None)

ctx.aa._fingertip_recompute = True
print(ctx.aa.value)

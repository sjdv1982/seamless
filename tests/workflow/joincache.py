# Disable LRU caches
from seamless.workflow.core.protocol.calculate_checksum import calculate_checksum_cache, checksum_cache
from seamless.workflow.core.protocol.deserialize import deserialize_cache
from seamless.workflow.core.protocol.serialize import serialize_cache
calculate_checksum_cache.disable()
checksum_cache.disable()
deserialize_cache.disable()
serialize_cache.disable()

import seamless
seamless.delegate(False)

from seamless.workflow.core.cache.buffer_cache import buffer_cache
from seamless.workflow.core.cache import CacheMissError

from seamless.workflow import Context, Cell
from seamless.workflow.core.manager.tasks.evaluate_expression import SerializeToBufferTask

old_run = SerializeToBufferTask._run
async def _run(self):
    print("SERIALIZE TO BUFFER", self.value)
    return await old_run(self)

SerializeToBufferTask._run = _run

ctx = Context()
ctx.a = Cell("int").set(2)
ctx.cell = Cell()
ctx.compute()
ctx.cell.a = ctx.a
print("START")
ctx.compute()
print(ctx.cell.value)
cs = ctx.cell.checksum.bytes()
print("RE-TRANSLATE 1")
ctx.translate(force=True)
ctx.compute() # "SERIALIZE TO BUFFER" must NOT be printed
print(ctx.cell.value)
print("DONE")
manager = ctx._manager
manager.cachemanager.join_cache.clear()
print("RE-TRANSLATE 2")
ctx.translate(force=True)
ctx.compute() # "SERIALIZE TO BUFFER" must be printed
print("DONE")
print("RE-TRANSLATE 3")
ctx.translate(force=True)
ctx.compute() # "SERIALIZE TO BUFFER" must NOT be printed
print("DONE")

buffer_cache.buffer_cache.pop(cs)
try:
    print(ctx.cell.value)
except CacheMissError as exc:
    print("CacheMissError", exc)  # Should not happen

buffer_cache.buffer_cache.pop(cs)
manager.cachemanager.rev_join_cache.clear()
manager.cachemanager.join_cache.clear()

try:
    print(ctx.cell.value)
except CacheMissError as exc:
    print("CacheMissError", exc)  # Should happen

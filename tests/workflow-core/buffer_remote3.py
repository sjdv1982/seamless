import seamless

seamless.delegate(level=2)
from seamless.workflow.core import context, cell
from seamless.workflow.core.cache.buffer_remote import can_read_buffer

cs = "3b1a2d4cf36b88daddecb57f0e26b6fa31654d3ff853866148d65bfa2b4e0951"
assert can_read_buffer(cs)

ctx = context(toplevel=True)
ctx.d = cell("mixed").set_checksum(cs)

ctx.compute()
print(ctx.d.value)

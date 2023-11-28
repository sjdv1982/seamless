import json
from pprint import pprint
import seamless
seamless.delegate(False)

from seamless.core import context, cell, StructuredCell
from seamless.highlevel import Checksum

ctx = context(toplevel=True)
ctx.data = cell("mixed")
ctx.sc = StructuredCell(
    data=ctx.data,
    inchannels=[()],
    outchannels=[("a",)]
)

ctx.a = cell("int")
ctx.sc.outchannels[("a",)].connect(ctx.a)

ctx.upstream = cell("mixed").set({"a": 42.9})
ctx.upstream.connect(ctx.sc.inchannels[()])

ctx.compute()
print(ctx.a.value)

livegraph = ctx._get_manager().livegraph
accessor = livegraph.cell_to_upstream[ctx.a]

from seamless.core.manager.tasks.evaluate_expression import build_expression_transformation
from seamless.core.cache.buffer_cache import buffer_cache
tf_checksum = build_expression_transformation(accessor.expression)
tfd = json.loads(buffer_cache.get_buffer(tf_checksum).decode())
pprint(tfd)


tf_result = seamless.run_transformation(tf_checksum, manager=ctx._get_manager())
print("expression-transformation", Checksum(tf_result))
print("cell                     ", ctx.a.checksum)
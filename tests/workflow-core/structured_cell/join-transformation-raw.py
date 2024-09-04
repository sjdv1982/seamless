import json
import sys
from pprint import pprint

import seamless

seamless.delegate(False)

from seamless import Checksum
from seamless.workflow.core import context, cell, StructuredCell

ctx = None
hash_pattern = {"*": "#"}

hp = hash_pattern
ctx = context(toplevel=True)
ctx.auth = cell("mixed", hash_pattern=hp)
ctx.data = cell("mixed", hash_pattern=hp)
ctx.buffer = cell("mixed", hash_pattern=hp)
ctx.schema = cell("plain")
ctx.sc = StructuredCell(
    auth=ctx.auth,
    buffer=ctx.buffer,
    data=ctx.data,
    schema=ctx.schema,
    inchannels=[("a",), ("b",), ("c",)],
    hash_pattern=hp,
)
s = ctx.sc.handle

ctx.a = cell("int").set(10)
ctx.b = cell("int").set(20)
ctx.c = cell("int").set(30)
ctx.a.connect(ctx.sc.inchannels[("a"),])
ctx.b.connect(ctx.sc.inchannels[("b"),])
ctx.c.connect(ctx.sc.inchannels[("c"),])


def adder(self, other):
    return other + self.x


s.x = 80
print(s.x.data)

ctx.compute()
pprint(ctx.buffer.value)
pprint(ctx.data.value)


def validate_x(self):
    assert self.x < 100


try:
    s.add_validator(validate_x)
except Exception:
    pprint(s.schema.value)

ctx.compute()

from seamless.workflow.core.manager.tasks.structured_cell import (
    build_join_transformation,
)
from seamless.workflow.core.cache.buffer_cache import buffer_cache

tf_checksum = build_join_transformation(ctx.sc)
tfd = json.loads(buffer_cache.get_buffer(tf_checksum).decode())
pprint(tfd)


pprint(tfd["structured_cell_join"])
tf_result = seamless.run_transformation(tf_checksum, manager=ctx._get_manager())
print("join-transformation", Checksum(tf_result))
print("structured cell    ", ctx.sc.checksum)

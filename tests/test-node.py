import seamless
from seamless import context, cell
from seamless.core.node import ScalarCellNode

ctx = context()
ctx.a = cell("int").set(10)
ctx.b = cell("json")

node = ScalarCellNode(ctx.a)

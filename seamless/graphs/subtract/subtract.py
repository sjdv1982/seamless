"""
A demo stdlib library that shows how it is done
"""

from seamless.highlevel import Context, Cell
import sys

# 1: Setup context

ctx = Context()
def subtract_func(a, b):
    print("A", a, "B", b)
    return a - b

def constructor(ctx, libctx, celltype, a, b, c):
    assert celltype in ("int", "float"), celltype
    ctx.a = Cell(celltype=celltype)
    ctx.b = Cell(celltype=celltype)
    ctx.c = Cell(celltype=celltype)
    a.connect(ctx.a)
    b.connect(ctx.b)
    c.connect_from(ctx.c)

    ctx.subtract = Transformer()
    ctx.subtract_code = Cell("code")
    ctx.subtract_code = libctx.subtract_code.value
    ctx.subtract.code = ctx.subtract_code
    ctx.subtract.a = ctx.a
    ctx.subtract.pins.a.celltype = celltype
    ctx.subtract.b = ctx.b
    ctx.subtract.pins.b.celltype = celltype
    ctx.c = ctx.subtract

ctx.subtract_code = Cell("code")
ctx.subtract_code = subtract_func
ctx.constructor_code = Cell("code")
ctx.constructor_code = constructor
ctx.constructor_params = {
    "celltype": "value",
    "a": {
        "type": "cell",
        "io": "input"
    },
    "b": {
        "type": "cell",
        "io": "input"
    },
    "c": {
        "type": "cell",
        "io": "output"
    },
}
ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the context in a library

from seamless.highlevel.library import LibraryContainer
mylib = LibraryContainer("mylib")
mylib.subtract = ctx
mylib.subtract.constructor = ctx.constructor_code.value
mylib.subtract.params = ctx.constructor_params.value

# 3: Run test example

ctx2 = Context()
ctx2.include(mylib.subtract)
ctx2.x = 10.0
ctx2.y = 3.0
ctx2.z = Cell("float")
ctx2.subtract = ctx2.lib.subtract(
    a=ctx2.x,
    b=ctx2.y,
    c=ctx2.z,
    celltype="float"
)
ctx2.compute()
print(ctx2.z.value)
print(ctx2.subtract.ctx.c.value)

if ctx2.z.value is None:
    sys.exit()

ctx2.compute()
ctx.compute()

# 3: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../subtract.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../subtract.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
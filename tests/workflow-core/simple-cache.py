"""
Retrieval of buffers and computation results from database cache
With Seamless delegation level 3 available:
    First, "export DELEGATE=1" to turn on delegation for simple.py
    Then run simple.py (with delegation)
    Finally, run this script 
"""

import seamless
from seamless.workflow.core import context, cell, transformer, unilink

seamless.config.block_local()  # Forbids Seamless to add 1 and 2 by itself

seamless.delegate(level=3)

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set_checksum(
    "bc4bb29ce739b5d97007946aa4fdb987012c647b506732f11653c5059631cd3d"  # 1
)
ctx.cell2 = cell("int").set_checksum(
    "191fb5fc4a9bf2ded9a09a0a2c4eb3eb90f15ee96deb1eec1a970df0a79d09ba"  # 2
)
ctx.code = cell("transformer").set_checksum(
    "1cbba7cc10e067273fdec7cc350d2b87508c1959d26bbab4f628f6f59ec49607"  # a + b
)
ctx.result = cell("int")
ctx.tf = transformer({"a": "input", "b": "input", "c": "output"})
ctx.cell1_unilink = unilink(ctx.cell1)
ctx.cell1_unilink.connect(ctx.tf.a)
ctx.cell2.connect(ctx.tf.b)
ctx.code_copy = cell("transformer")
ctx.code.connect(ctx.code_copy)
ctx.code_copy.connect(ctx.tf.code)
ctx.result_unilink = unilink(ctx.result)
ctx.tf.c.connect(ctx.result_unilink)
ctx.result_copy = cell("int")
ctx.result.connect(ctx.result_copy)
ctx.compute()
print(ctx.cell1, ctx.cell1.value)  # Retrieved from database value cache
print(ctx.cell2, ctx.cell2.value)  # Retrieved from database value cache
print(ctx.code, ctx.code.value)  # Retrieved from database value cache
print(ctx.result.checksum)  #  checksum from database transformer result cache
print(ctx.result.value)  #  3 is the value that corresponds to a3b..27e
#  This is also retrieved from database value cache
print(ctx.tf.status)
print(ctx.status)

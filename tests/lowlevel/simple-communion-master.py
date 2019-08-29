# Start simple-communion-slave first, and keep it running

import sys, os, asyncio
os.environ["SEAMLESS_COMMUNION_ID"] = "simple-communion-master"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
from seamless.core import context, cell

ctx = context(toplevel=True)
ctx.equilibrate()

ctx.cell1 = cell("int").set_checksum(
    "bc4bb29ce739b5d97007946aa4fdb987012c647b506732f11653c5059631cd3d"  # 1
)
ctx.cell2 = cell("int").set_checksum(
    "191fb5fc4a9bf2ded9a09a0a2c4eb3eb90f15ee96deb1eec1a970df0a79d09ba"  # 2
)
ctx.code = cell("transformer").set_checksum(
    "1cbba7cc10e067273fdec7cc350d2b87508c1959d26bbab4f628f6f59ec49607"  # a + b
)
print(ctx.cell1, ctx.cell1.value) 
print(ctx.cell2, ctx.cell2.value) 
print(ctx.code, ctx.code.value)   

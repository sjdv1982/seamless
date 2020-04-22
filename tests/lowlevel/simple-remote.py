# run scripts/jobslave-noredis.py 

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "simple-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
seamless.set_ncores(0)
from seamless import communion_server

communion_server.configure_master(
    buffer=True,
    transformation_job=True,
    transformation_status=True,
)

from seamless.core import context, cell, transformer, unilink

ctx = context(toplevel=True)
ctx.cell1 = cell().set(1)
ctx.cell2 = cell().set(2)    
ctx.result = cell()
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.cell1_unilink = unilink(ctx.cell1)
ctx.cell1_unilink.connect(ctx.tf.a)    
ctx.cell2.connect(ctx.tf.b)
ctx.code = cell("transformer").set("c = a + b")
ctx.code.connect(ctx.tf.code)
ctx.result_unilink = unilink(ctx.result)
ctx.tf.c.connect(ctx.result_unilink)
ctx.result_copy = cell()
ctx.result.connect(ctx.result_copy)

print(ctx.cell1.value)
print(ctx.code.value)
ctx.compute()
print(ctx.result.value, ctx.status)
print(ctx.tf.exception)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value, ctx.status)
ctx.code.set("c = a + b + 1000")
ctx.compute()
print(ctx.result.value, ctx.status)

print("Introduce delay...")
ctx.code.set("import time; time.sleep(2); c = -(a + b)")
ctx.compute(1.0)
print("after 1.0 sec...")
print(ctx.result.value, ctx.status)
print("...")
ctx.compute()
print(ctx.result.value, ctx.status)

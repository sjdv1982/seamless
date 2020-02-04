# first start scripts/jobslave-noredis.py
import os
os.environ["SEAMLESS_COMMUNION_ID"] = "simple-remote2"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"


import seamless
seamless.set_ncores(0)

from seamless import communion_server

communion_server.configure_master(
    buffer=True,
    transformation_job=True,
    transformation_status=True,
)

from seamless.core import context, cell, transformer, link

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
def progress(a, b):
    import time
    for n in range(10):
        print("PROGRESS", b, n+1)
        set_progress((n+1)/10* 100)
        if (n % 2) == 0:
            return_preliminary((n+1)/10*(a+b))
        time.sleep(1)
    return a + b
ctx.code = cell("transformer").set(progress)
ctx.result = cell("float")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.code.connect(ctx.tf.code)
ctx.cell1.connect(ctx.tf.a)
ctx.cell2.connect(ctx.tf.b)
ctx.tf.c.connect(ctx.result)

def report():
    print("TF       ", ctx.tf.status)
    v1 = "%.3f" % ctx.result.value if ctx.result.value is not None else None
    print("RESULT       ", v1, ctx.result.status)
    print()

for n in range(5):
    ctx.compute(0.5)
    report()

ctx.cell2.set(100)

for n in range(20):
    ctx.compute(0.5)
    report()

ctx.compute()
report()

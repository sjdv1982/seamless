# first start scripts/jobslave-noredis.py
import os
os.environ["SEAMLESS_COMMUNION_ID"] = "simple-duplex-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"


import seamless
seamless.set_ncores(0)

from seamless import communion_server

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

from seamless.core import context, cell, transformer, unilink

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
def progress(a, b):
    import time
    for n in range(10):
        print("PROGRESS", n+1)
        set_progress((n+1)/10* 100)
        if (n % 2) == 0:
            return_preliminary((n+1)/10*(a+b))
        time.sleep(1)
    return a + b
ctx.code = cell("transformer").set(progress)
ctx.result = cell("float")
ctx.result_duplex = cell("float")
ctx.tf = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.tf_duplex = transformer({
    "a": "input",
    "b": "input",
    "c": "output"
})
ctx.code.connect(ctx.tf.code)
ctx.code.connect(ctx.tf_duplex.code)
ctx.cell1.connect(ctx.tf.a)
ctx.cell1.connect(ctx.tf_duplex.a)
ctx.cell2.connect(ctx.tf.b)
ctx.cell2.connect(ctx.tf_duplex.b)
ctx.tf.c.connect(ctx.result)
ctx.tf_duplex.c.connect(ctx.result_duplex)

def report():
    print("TF       ", ctx.tf.status)
    print("TF DUPLEX", ctx.tf_duplex.status)
    v1 = "%.3f" % ctx.result.value if ctx.result.value is not None else None
    v2 = "%.3f" % ctx.result_duplex.value \
      if ctx.result_duplex.value is not None else None
    print("RESULT       ", v1, ctx.result.status)
    print("RESULT DUPLEX", v2, ctx.result_duplex.status)
    print()

for n in range(5):
    ctx.compute(0.5)
    report()

ctx.tf.cancel()
ctx.compute(0.5)
report()
print("EXCEPTION       ", ctx.tf.exception)
print("EXCEPTION DUPLEX", ctx.tf_duplex.exception)
print()


ctx.tf.clear_exception()
print("EXCEPTION       ", ctx.tf.exception)
print("EXCEPTION DUPLEX", ctx.tf_duplex.exception)
print()

for n in range(20):
    ctx.compute(0.5)
    report()

ctx.compute()
report()

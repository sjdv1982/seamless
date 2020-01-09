import seamless
seamless.deactivate_transformations()

from seamless import communion_server

from seamless.core import context, cell, transformer

from seamless import RedisSink
sink = RedisSink()

ctx = context(toplevel=True)
ctx.cell1 = cell("int").set(1)
ctx.cell2 = cell("int").set(2)
def progress(a, b):
    import time
    for n in range(10):
        print("TRANSFORMATION PROGRESS", b, n+1)
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

print(ctx.tf.get_transformation())

"""
for n in range(3):
    ctx.compute(0.5)
    report()


print("START")
seamless.activate_transformations()
for n in range(12):
    ctx.compute(1)
    report()
"""
import seamless
from seamless.workflow.core import context, cell, transformer

seamless.load_vault("./reuse-vault")
seamless.delegate(level=0, force_database=True)

ctx = context(toplevel=True)


def func(a, b):
    import time

    time.sleep(3)
    return a + b + 0.5


ctx.a = cell().set(1)
ctx.b = cell().set(2)
ctx.tf = transformer({"a": "input", "b": "input", "result": "output"})
ctx.result = cell()
ctx.code = cell("python").set(func)
ctx.compute()
seamless.config.block_local()
ctx.a.connect(ctx.tf.a)
ctx.b.connect(ctx.tf.b)
ctx.code.connect(ctx.tf.code)
ctx.tf.result.connect(ctx.result)

ctx.compute()
print(ctx.status)
print(ctx.result.value)
print(ctx.tf.exception)
# print(ctx.tf.execution_metadata)

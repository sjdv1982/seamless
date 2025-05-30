import seamless
import os

if "DELEGATE" in os.environ:
    has_err = seamless.delegate()
    if has_err:
        exit(1)
else:
    has_err = seamless.delegate(level=3)
    if has_err:
        exit(1)
    from seamless.workflow.core.transformation import get_global_info

    get_global_info()  # avoid timing errors

from seamless.workflow import Context

ctx = Context()

from seamless import transformer


@transformer
def func2(a, b):
    @transformer
    def func(a, b):
        import time

        time.sleep(0.4)
        return 100 * a + b

    return func(a, b) + func(b, a)


ctx.tf = func2
ctx.tf.a = 21
ctx.tf.b = 17
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)
print("")

print(func2(21, 17))
print(func2(22, 18))


@transformer
def func2a(a, b):
    @transformer
    def func(a, b):
        import time

        time.sleep(2)
        return 100 * a + b

    return func(a, b) + func(b, a)


print(func2a(29, 12))

# transformer within transformer within transformer...

import seamless.workflow.config

if "DELEGATE" in os.environ:
    seamless.workflow.config.unblock_local()


@transformer
def func3(a, b):

    @transformer
    def func2b(a, b):
        @transformer
        def func(a, b):
            import time

            time.sleep(2)
            return 100 * a + b

        return func(a, b)

    return func2b(a, b) + func2b(b, a)


ctx.tf.code = func3
ctx.tf.meta = {"local": True}
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 33
ctx.tf.b = 33
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 7
ctx.tf.b = 22
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

if "DELEGATE" in os.environ:
    seamless.workflow.config.block_local()

print(func3(7, 22))
print(func3(101, 720))

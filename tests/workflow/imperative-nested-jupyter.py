import seamless

seamless.delegate(level=3)

from seamless.workflow import Context
from seamless.workflow.core.transformation import SeamlessTransformationError
import traceback

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
await ctx.computation()
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

    # func.local = False

    return func(a, b) + func(b, a)


print(func2a(29, 12))

# transformer within transformer within transformer...


@transformer
def func3(a, b):

    @transformer
    def func2b(a, b):
        @transformer
        def func(a, b):
            import time

            time.sleep(2)
            return 100 * a + b

        # func.local = False
        return func(a, b)

    func2b.local = True

    return func2b(a, b) + func2b(b, a)


ctx.tf.code = func3
ctx.tf.meta = {"local": True}
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 33
ctx.tf.b = 33
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

ctx.tf.a = 7
ctx.tf.b = 22
await ctx.computation()
print(ctx.tf.logs)
print(ctx.tf.status)
print(ctx.tf.result.value)

print(func3(7, 22))
print(func3(101, 720))

import seamless
import traceback

seamless.delegate(False)

from seamless import transformer


@transformer
def func(a, b):
    return 10 * a + 2 * b


print(func(20, 6))

seamless.config.block_local()


@transformer(in_process=True)
def func2(a, b):
    return 10 * a + 2 * b


print(func2(30, 12))

try:
    print(func(40, 2))
except RuntimeError:
    traceback.print_exc(limit=0)

print(func2(40, 2))

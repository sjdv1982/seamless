import seamless

seamless.delegate()

from seamless import transformer


@transformer
def func(a, b):
    import time

    time.sleep(20)
    return 100 * a + b


func.local = False

from asyncio.exceptions import TimeoutError

try:
    result = func(1, 2)  # takes 20 sec
except TimeoutError:
    print("Timeout")
    exit(1)
print(result)
result = func(1, 2)  # takes 0.5 sec
print(result)

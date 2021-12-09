from seamless.highlevel import Context
import asyncio

ctx = Context()

def func(a, delay):
    import sys
    print("FUNC", a, delay, file=sys.stderr)
    import time
    for n in range(int(delay)):
        print("DELAY", n+1, delay)
        time.sleep(1)
    return a + 0.1 * delay + 1000

ctx.tf1 = func
ctx.tf1.a = 1
ctx.tf1.delay = 5
ctx.tf1.debug.direct_print = True
logs_file = "/tmp/logs_file.out"
ctx.tf1.debug.logs_file = logs_file
ctx.result = ctx.tf1
ctx.compute()
print(ctx.tf1.logs)
print()
print("Logs file content:")
print()
with open(logs_file) as lf:
    print(lf.read())
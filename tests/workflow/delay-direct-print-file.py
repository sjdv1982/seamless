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
ctx.result = ctx.tf1
ctx.compute()
ctx.tf1.delay = 10
print("Print to file /tmp/direct-print.out")
ctx.tf1.debug.direct_print_file = "/tmp/direct-print.out"
ctx.compute()
import os
print("Content of /tmp/direct-print.out")
os.system("cat /tmp/direct-print.out")
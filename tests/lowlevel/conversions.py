import asyncio
import json
from seamless.core import context, cell

ctx = context(toplevel=True)

value = [42, "test", {"mykey": "myvalue"}, True]
value_json = json.dumps(value)

import time
start_time = time.time()
print_ORIGINAL = print

loop = asyncio.get_event_loop()

def print(*args):
    args = [str(arg) for arg in args]
    elapsed_time = time.time() - start_time
    print_ORIGINAL("Time: %.1f ms," % (1000 * elapsed_time), *args)

ctx.txt1 = cell("text")
ctx.txt2 = cell("text")
ctx.txt3 = cell("text")
ctx.txt4 = cell("text")
ctx.plain = cell("plain")

print("*** Start ***")
ctx.txt1.set(value_json)

print("*** Stage 1a ***")
print("ctx.txt1", ctx.txt1.data)

ctx.txt2.set(ctx.txt1.data)
print("*** Stage 1b ***")
ctx.equilibrate()
ctx.txt3.set(ctx.txt1.data)

print("*** Stage 1c ***")
print("ctx.txt2", ctx.txt2.data)
print("ctx.txt3", ctx.txt3.data)

print("*** Stage 2 ***")
ctx.txt3.connect(ctx.txt4)
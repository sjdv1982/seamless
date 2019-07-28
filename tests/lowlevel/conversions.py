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
    if not len(args):
        print_ORIGINAL()   
        return 
    args = [str(arg) for arg in args]
    elapsed_time = time.time() - start_time
    print_ORIGINAL("Time: %.1f ms," % (1000 * elapsed_time), *args)

ctx.txt1 = cell("text")
ctx.txt2 = cell("text")
ctx.txt3 = cell("text")
ctx.txt4 = cell("text")
ctx.plain = cell("plain")
ctx.plain2 = cell("plain")

print("*** Start ***")
print(ctx.txt1.value)
print()

print("*** Stage 0 ***")
ctx.txt1.set(value_json)
print()

print("*** Stage 1a ***")
value = ctx.txt1.data
print("ctx.txt1", value)

print("*** Stage 1b ***")
ctx.txt2.set(value)
ctx.txt3.set(value)

print("*** Stage 1c ***")
print("ctx.txt2", ctx.txt2.data)
print("ctx.txt3", ctx.txt3.data)
print()

print("*** Stage 2 ***")
ctx.txt3.connect(ctx.txt4)
ctx.equilibrate()
print("ctx.txt4", ctx.txt4.data)
print()

print("*** Stage 3 ***")
ctx.txt1.connect(ctx.plain)
ctx.equilibrate()
print("ctx.plain", ctx.plain.data)

print("*** Stage 3a ***")
ctx.txt3.connect(ctx.plain2)
ctx.equilibrate()
print("ctx.plain2", ctx.plain2.data)
print()

print("STOP")
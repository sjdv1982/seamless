import asyncio
import json
from seamless.core import context, cell

ctx = context(toplevel=True)

value = [42, "test", {"mykey": "myvalue"}, True]
value_json = json.dumps(value)

import time
start_time = time.time()
print_ORIGINAL = print

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
ctx.mixed = cell("mixed")

print("*** Start ***")
print(ctx.txt1.value)
print()

print("*** Stage 0 ***")
ctx.txt1.set(value_json)
print()

print("*** Stage 1a ***")
ctx.compute()
value = ctx.txt1.data
print("ctx.txt1", value)

print("*** Stage 1b ***")
ctx.txt2.set(value)
ctx.txt3.set(value)

print("*** Stage 1c ***")
ctx.compute()
print("ctx.txt2", ctx.txt2.data)
print("ctx.txt3", ctx.txt3.data)
print()

print("*** Stage 2 ***")
ctx.txt3.connect(ctx.txt4)
ctx.compute()
print("ctx.txt4", ctx.txt4.data)
print()

print("*** Stage 3 ***")
ctx.txt1.connect(ctx.plain)
ctx.compute()
print("ctx.plain", ctx.plain.data)

print("*** Stage 3a ***")
ctx.txt3.connect(ctx.plain2)
ctx.compute()
print("ctx.plain2", ctx.plain2.data)

print("*** Stage 3b ***")
ctx.txt3.connect(ctx.mixed)
ctx.compute()
print("ctx.mixed", ctx.mixed.data)

print("*** Stage 4 ***")
ctx.ipy = cell("ipython").set("""
%%timeit
x = 42

""")
ctx.py = cell("python")
ctx.ipy.connect(ctx.py)
ctx.compute()
print("ctx.py", ctx.py.data)
print()

print("*** Stage 5 ***")
ctx.plain3 = cell("plain").set("Test string!!")
ctx.text = cell("text")
ctx.plain3.connect(ctx.text)
ctx.str = cell("str")
ctx.plain3.connect(ctx.str)
ctx.compute()
print("ctx.plain3", ctx.plain3.data, ctx.plain3.buffer)
print("ctx.text", ctx.text.data, ctx.text.buffer)
print("ctx.str", ctx.str.data, ctx.str.buffer)

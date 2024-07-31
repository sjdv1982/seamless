import seamless
seamless.delegate(False)

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
print("ctx.plain2", ctx.plain2.data, type(ctx.plain2.data).__name__) # list

print("*** Stage 3b ***")
ctx.txt3.connect(ctx.mixed)  # NOT text-to-plain!
ctx.compute()
print("ctx.mixed", ctx.mixed.data, type(ctx.mixed.data).__name__) # str

print("*** Stage 4 ***")
ctx.ipy = cell("ipython").set("""
%%timeit
x = 42

""")
ctx.py = cell("python")
ctx.ipy.connect(ctx.py)
ctx.compute()
print("ctx.ipy", ctx.ipy.data)
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
print()

print("*** Stage 6 ***")
ctx.bool = cell("bool").set(1)
ctx.int = cell("int")
ctx.bool.connect(ctx.int)
ctx.plain4 = cell("plain")
ctx.plain4.connect_from(ctx.bool)
ctx.plain5 = cell("plain")
ctx.plain5.connect_from(ctx.int)
ctx.bool2 = cell("bool")
ctx.bool2.connect_from(ctx.plain4)
ctx.compute()
print("ctx.bool", ctx.bool.data, ctx.bool.buffer, ctx.bool.checksum)
print("ctx.plain4", ctx.plain4.data, ctx.plain4.buffer, ctx.plain4.checksum)
print("ctx.int", ctx.int.value, ctx.int.checksum)
print("ctx.plain5", ctx.plain5.value, ctx.plain5.checksum)
print("ctx.bool2", ctx.bool2.data, ctx.bool2.buffer, ctx.bool2.checksum)
print()
ctx.bool.set(0)
ctx.compute()
print("ctx.bool", ctx.bool.data, ctx.bool.buffer, ctx.bool.checksum)
print("ctx.plain4", ctx.plain4.data, ctx.plain4.buffer, ctx.plain4.checksum)
print("ctx.int", ctx.int.value, ctx.int.checksum)
print("ctx.plain5", ctx.plain5.value, ctx.plain5.checksum)
print("ctx.bool2", ctx.bool2.data, ctx.bool2.buffer, ctx.bool2.checksum)
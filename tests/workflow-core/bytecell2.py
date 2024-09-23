import seamless

seamless.delegate(False)

from seamless.workflow.core import context, cell

ctx = context(toplevel=True)
ctx.bytes1 = cell("bytes")
ctx.bytes1.set(b"this is a bytes value")

ctx.bin = cell("binary")
ctx.bytes1.connect(ctx.bin)

ctx.bytes2 = cell("bytes")
ctx.bin.connect(ctx.bytes2)

ctx.mix = cell("mixed")
ctx.bytes1.connect(ctx.mix)

ctx.bytes3 = cell("bytes")
ctx.mix.connect(ctx.bytes3)

ctx.compute()
print(ctx.bytes1.buffer)
print(ctx.bytes1.value, type(ctx.bytes1.value))
print()

print("Exception:", ctx.bin.exception)
print(ctx.bin.buffer)
print(ctx.bin.value, type(ctx.bin.value))
print()

print("Exception:", ctx.bytes2.exception)
print(ctx.bytes2.buffer)
print(ctx.bytes2.value, type(ctx.bytes2.value))
print()

print("Exception:", ctx.mix.exception)
print(ctx.mix.buffer)
print(ctx.mix.value, type(ctx.mix.value))
print()

print("Exception:", ctx.bytes3.exception)
print(ctx.bytes3.buffer)
print(ctx.bytes3.value, type(ctx.bytes3.value))
print()

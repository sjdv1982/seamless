import seamless
seamless.delegate(False)

from seamless.workflow.core import context, cell
ctx = context(toplevel=True)
ctx.bytes1 = cell("bytes")
ctx.bytes1.set(b'this is a bytes value')
ctx.compute()
print(ctx.bytes1.buffer)
print(ctx.bytes1.value, type(ctx.bytes1.value))
print()

from seamless.buffer.convert import try_convert
binary_cs = try_convert(
    ctx.bytes1.checksum,
    "bytes",
    "binary",
    buffer=ctx.bytes1.buffer
)
print(binary_cs)
print()

ctx.bin = cell("binary")
ctx.bytes1.connect(ctx.bin)
ctx.compute()
print("Exception:", ctx.bin.exception)
print(ctx.bin.checksum)
print(ctx.bin.buffer)
print(ctx.bin.value, type(ctx.bin.value))
print()

ctx.bytes2 = cell("bytes")
ctx.bin.connect(ctx.bytes2)
ctx.compute()
print("Exception:", ctx.bytes2.exception)
print(ctx.bytes2.buffer)
print(ctx.bytes2.value, type(ctx.bytes2.value))
print()

ctx.mix = cell("mixed")
ctx.bytes1.connect(ctx.mix)
ctx.compute()
print("Exception:", ctx.mix.exception)
print(ctx.mix.buffer)
print(ctx.mix.value, type(ctx.mix.value))
print()

ctx.plain = cell("mixed")
ctx.bytes1.connect(ctx.plain)
ctx.compute()
print("Exception:", ctx.plain.exception)
print(ctx.plain.buffer)
print(ctx.plain.value, type(ctx.plain.value))
print()

ctx.bytes3 = cell("bytes")
ctx.mix.connect(ctx.bytes3)
ctx.compute()
print("Exception:", ctx.bytes3.exception)
print(ctx.bytes3.buffer)
print(ctx.bytes3.value, type(ctx.bytes3.value))
print()
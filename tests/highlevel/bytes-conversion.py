from seamless.highlevel import Context, Cell

ctx = Context()
ctx.bin1 = Cell()
ctx.bin1.celltype = "bytes"
ctx.bin1.set(b'this is a bytes value')
ctx.compute()
print(ctx.bin1.buffer)
print(ctx.bin1.value)
ctx.mix = ctx.bin1
ctx.bin2 = ctx.mix
ctx.bin2.celltype = "bytes"
ctx.compute()
print(ctx.bin1.value)
print(ctx.mix.value.unsilk, type(ctx.mix.value.unsilk))
print(ctx.bin2.value, type(ctx.bin2.value))
from seamless.highlevel import Context
ctx = Context()
ctx.a = {"x": 123}
z = ctx.get_zip()
print("ZIP size:", len(z))
ctx.b = ctx.a.x
ctx.compute()
print(ctx.b.value, ctx.b.checksum)
z = ctx.get_zip()
print("ZIP size:", len(z))
ctx.b.scratch = True
ctx.compute()
print(ctx.b.value, ctx.b.checksum)
z = ctx.get_zip()
print("ZIP size (should be 241):", len(z))
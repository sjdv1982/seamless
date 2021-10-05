from seamless.highlevel import Context

ctx = Context()
fallback_ctx = Context()

ctx.a = 5
ctx.b = 7
ctx.tf = lambda a,b: a * b
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.result = ctx.tf.result
ctx.reresult = ctx.result
ctx.compute()
print(ctx.result.value)

print(1)
fallback_ctx.result2 = 42
fallback_ctx.translate()
ctx.result.fallback(fallback_ctx.result2)
ctx.compute()
print(ctx.result.value, ctx.reresult.value)
print()

print(2)
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value, ctx.reresult.value)
print()

print(3)
fallback_ctx.translate(force=True)
print(ctx.result.value, ctx.reresult.value)
fallback_ctx.result2 = 45
fallback_ctx.compute()
print(ctx.result.value, ctx.reresult.value)
print()
exit(0)

print(4)
ctx.a = 10
ctx.compute()
print(ctx.result.value, ctx.reresult.value)
print()

print(5)
ctx.result.fallback(None)
ctx.compute()
print(ctx.result.value, ctx.reresult.value)
ctx.b = 20
ctx.compute()
print(ctx.result.value, ctx.reresult.value)
print()

print(6)
fallback_ctx.a2 = 2
ctx.result.fallback(fallback_ctx.result2)
ctx.a.fallback(fallback_ctx.a2)
ctx.compute()
print(ctx.result.value)
fallback_ctx.a2 = 3
ctx.compute()
print(ctx.result.value)
ctx.result.fallback(None)
ctx.compute()
print(ctx.result.value)
ctx.b = 4
ctx.compute()
print(ctx.result.value)
print()


# TODO: test only_none
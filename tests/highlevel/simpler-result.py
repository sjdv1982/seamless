from seamless.highlevel import Context

ctx = Context()

ctx.a = 12

def triple_it(a):
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.transform.example.a = 99
ctx.transform.with_result = True
ctx.transform.result.example.set(100)
print(ctx.transform.result.schema)
ctx.myresult = ctx.transform
ctx.compute()
print(ctx.myresult.value)
print(ctx.status)
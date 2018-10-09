from seamless.highlevel import Context

ctx = Context()

ctx.a = 12

def triple_it(a):
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.transform._get_htf()["with_result"] = True
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)
print(ctx.transform.result.value)

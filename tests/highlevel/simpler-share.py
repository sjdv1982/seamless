from seamless.highlevel import Context, Transformer

ctx = Context()

ctx.a = 12
ctx.a.share() #requires translate() to have an effect

def triple_it(a):
    return 3 * a

ctx.transform = triple_it
ctx.code >> ctx.transform.code
ctx.code.share()
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.myresult.share()
ctx.equilibrate()
print(ctx.myresult.value)

ctx.a = 13
ctx.equilibrate()
print(ctx.myresult.value)

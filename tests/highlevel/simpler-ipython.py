from seamless.highlevel import Context, Transformer

ctx = Context()

ctx.a = 12

ipycode = """
%%timeit
def triple_it(a):
    return 3 * a
"""
ctx.transform = Transformer()
ctx.transform.language = "ipython"
ctx.transform.code = ipycode
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.compute()
print(ctx.myresult.value) # None

ctx.a = 13
ctx.compute()
print(ctx.myresult.value) # None
print(ctx.transform.status)

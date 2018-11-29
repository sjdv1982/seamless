from seamless import Context, Transformer

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
ctx.equilibrate()
print(ctx.myresult.value)

ctx.a = 13
ctx.equilibrate()
print(ctx.myresult.value)

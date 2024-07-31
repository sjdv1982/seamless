import seamless
from seamless.workflow import Context, Transformer

seamless.delegate(False)

ctx = Context()

ctx.a = 12

ipycode = """
%%timeit
def triple_it(a):
    return 3 * a

result = _
"""
ctx.transform = Transformer()
ctx.transform.language = "ipython"
ctx.transform.code = ipycode
ctx.transform.a = ctx.a
ctx.transform.debug.direct_print = True
ctx.myresult = ctx.transform
ctx.compute()
print(ctx.myresult.value) # None

ctx.a = 13
ctx.compute()
print(ctx.myresult.value) # None
print(ctx.transform.status)

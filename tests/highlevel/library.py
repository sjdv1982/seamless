from seamless.highlevel import Context, stdlib

ctx = Context()

ctx.a = 12
ctx.a._get_hcell()["format"] = "plain" ###

def triple_it(a, **kwargs):
    print("triple", a, kwargs)
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)

stdlib.triple_it = ctx
#ctx.transform.b = 777
ctx.equilibrate()
print(ctx.myresult.value)

print("START")
ctx2 = Context()
ctx2.sub = stdlib.triple_it
ctx2.sub2 = stdlib.triple_it
ctx2.equilibrate()

print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)

def double_it(a, **kwargs):
    print("double", a, kwargs)
    return 2 * a
stdlib.triple_it.transform.code = double_it
print(stdlib.triple_it.transform._get_tf().code.value)
stdlib.triple_it.equilibrate()
print(stdlib.triple_it.myresult.value)

ctx2.equilibrate()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)

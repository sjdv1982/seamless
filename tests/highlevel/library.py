from seamless.highlevel import Context, stdlib

ctx = Context()
ctx.a = 12

def triple_it(a, **kwargs):
    print("triple", a, kwargs)
    return 3 * a

ctx.transform = triple_it
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
###ctx.equilibrate()
print(ctx.myresult.value)

ctx.transform.b = 777
ctx.translate(force=True)
stdlib.triple_it = ctx

print("START")
ctx2 = Context()
ctx2.sub = stdlib.triple_it
ctx2.sub2 = stdlib.triple_it
ctx2.equilibrate()

print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)
print(ctx2.sub.transform.a.value)
print(ctx2.sub.transform.b.value)

print("UPDATE...")
def double_it(a, **kwargs):
    print("double", a, kwargs)
    return 2 * a
stdlib.triple_it.transform.code = double_it
stdlib.triple_it.register_library()

print("UPDATE")
ctx2.equilibrate()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)
print(ctx2.sub.transform.b.value)

print("UPDATE 2...")
stdlib.triple_it.transform.b = 888
stdlib.triple_it.equilibrate()
stdlib.triple_it.register_library()
print("UPDATE 2")
ctx2.equilibrate()
print(ctx2.sub.myresult.value)
print(ctx2.sub2.myresult.value)
print(ctx2.sub.transform.b.value)

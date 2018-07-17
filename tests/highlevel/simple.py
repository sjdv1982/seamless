from seamless.highlevel import Context

# 0
ctx = Context()
ctx.mount("/tmp/mount-test")

# 1
ctx.a = 10
print(ctx.a.value)

# 1a
ctx.a = 12
ctx.translate()
print(ctx.a.value)

# 2
def double_it(a):
    return 2 * a

ctx.transform = double_it
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.equilibrate()
print(ctx.myresult.value)

# 3
ctx.a = 12
ctx.equilibrate()
print(ctx.myresult.value)

# 4
def triple_it(a):
    return 3 * a
ctx.transform.code = triple_it
ctx.equilibrate()
print(ctx.myresult.value)

# 5
ctx.tfcode >> ctx.transform.code
ctx.transform.b = 100
def triple_it2(a, b):
    return 3 * a + b
ctx.tfcode = triple_it2
ctx.equilibrate()
print(ctx.myresult.value)
import sys; sys.exit()

# 6
ctx.translate(force=True)
ctx.equilibrate()
print(ctx.myresult.value)

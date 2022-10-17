module_code = """
a = 20
def func(x,y):
    print("X: {}, Y: {}".format(x,y))
    return x * y + a
"""

from seamless.highlevel import Context, Module

ctx = Context()
ctx.mod = Module()
ctx.mod.code = module_code

def run():
    return mod.func(10, 7)

ctx.run = run
ctx.run.mod = ctx.mod
ctx.compute()
print(ctx.run.status)
print(ctx.run.logs)
print()

a = ctx.mod.module.a
print(a)
func = ctx.mod.module.func
print(func(10,7))
print()

module_code = """
a = 30
def func(x,y):
    print("X = {}, Y = {}".format(x,y))
    return x * y + a
"""
ctx.mod.code = module_code
ctx.compute()

print(a)
a = ctx.mod.module.a
print(a)
print()

print(func(10,7))
func = ctx.mod.module.func
print(func(10,7))
print()
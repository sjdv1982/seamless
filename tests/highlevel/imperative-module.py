raise NotImplementedError

from seamless.highlevel import Context, Cell, Module
from seamless.imperative import transformer

ctx = Context()

ctx.pypackage = Module()
ctx.pypackage.multi = True
ctx.pypackage.mount("debugmount/pypackage")
ctx.compute()
print(ctx.pypackage._get_ctx().code.value)
print(ctx.pypackage._get_ctx().module_cell.value)
print()
print("Stage 1")

@transformer
def func(a, b):
    from .pypackage import get_square
    aa = get_square(a)
    bb = get_square(b)
    return aa+bb + 0

ctx.tf = func
ctx.tf.debug.direct_print = True
ctx.tf.pypackage = ctx.pypackage
ctx.tf.a = 8
ctx.tf.b = 9
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.logs)
print("/stage 1")

import sys
sys.path.append("debugmount")
import pypackage

func.modules.pypackage = pypackage

print(func(12, 13))

import seamless
seamless.database_cache.connect()
seamless.database_sink.connect()

@transformer
def func2(a,b):
    
    @transformer
    def func(a, b):
        from .pypackage2 import get_square
        aa = get_square(a)
        bb = get_square(b)
        return aa+bb
    func.modules.pypackage2 = pypackage
    func.blocking = False
    result = func(a, b) 
    print("func RESULT LOGS", result.logs)
    print("func RESULT VALUE", result.value)
    return result.value

ctx.tf.code = func2
print("Stage 2")
ctx.compute()
print(ctx.tf.logs)
print(ctx.tf.result.value)
print("/stage 2")

print("Stage 3")
func2.modules.pypackage = pypackage
func2.blocking = False
result = func2(17, 18)
print(result.logs)
print(result.value)
result = func2(9, 10)
print(result.logs)
print(result.value)
print("/stage 3")

print("Stage 4")
def func3(a,b,c):

    @transformer
    def func2(a,b):
        
        @transformer
        def func(a, b):
            from .pypackage2 import get_square
            aa = get_square(a)
            bb = get_square(b)
            return aa+bb
        func.modules.pypackage2 = pypackage
        func.blocking = False
        result = func(a, b) 
        print("func RESULT LOGS", result.logs)
        print("func RESULT VALUE", result.value)
        return result.value
    func2.modules.pypackage = pypackage
    return func2(a, b) + func2(b, c)

print(func3(17,18,19), 17**2 + 2*18**2 + 19**2)
print("/stage 4")
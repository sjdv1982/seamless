"""
Dynamic workflow example
"""
from seamless.highlevel import Context

def switch(input, which):
    return {which: input}

def merge(input, which):
    return input.get(which)

def func1(v):
    return v + 42

def func2(v):
    return -2 * v

ctx = Context()
ctx.merge = merge
ctx.a = 1000
ctx.which = "a"
ctx.switch = switch
ctx.switch.input = ctx.a
ctx.switch.which = ctx.which
ctx.switched = ctx.switch
ctx.func1 = func1
ctx.switched_a = ctx.switched.a
ctx.func1.v = ctx.switched_a
ctx.func2 = func2
ctx.switched_b = ctx.switched.b
ctx.func2.v = ctx.switched_b
ctx.tomerge = {}
ctx.func1_result = ctx.func1
ctx.func2_result = ctx.func2
ctx.tomerge.a = ctx.func1_result
ctx.tomerge.b = ctx.func2_result
ctx.merge.input = ctx.tomerge
ctx.merge.pins.input.celltype = "plain"
ctx.merge.which = ctx.which
ctx.merged = ctx.merge
ctx.compute()
print(ctx.merged.value)
ctx.which = "b"
ctx.compute()
print(ctx.merged.value)
ctx.which = "c"
ctx.compute()
print(ctx.merged.value)

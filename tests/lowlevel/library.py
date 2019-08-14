from seamless.core import context, cell, transformer, macro, libcell
from seamless.core import library
from seamless.core import macro_mode_on

def compute_pi(iterations):
    from math import sqrt
    x = 0
    for n in range(iterations):
        m = n + 1
        x += 1.0/(m * m)
    pi = sqrt(6 * x)
    return pi

def load(ctx):
    ctx.readme = libcell(".readme")
    ctx.tf = transformer({
        "iterations": "input",
        "pi": "output"
    })
    ctx.code = libcell(".code")
    ctx.code.connect(ctx.tf.code)
    ctx.iterations = cell()
    ctx.iterations.connect(ctx.tf.iterations)
    ctx.result = cell()
    ctx.tf.pi.connect(ctx.result)

lctx = context(toplevel=True)
lctx.readme = cell("text").set("Compute pi iteratively")
lctx.code = cell("python").set(compute_pi)
lctx.load = cell("macro").set(load)
lctx.equilibrate()
lib, root = library.build(lctx)
library.register("compute", lib, root)

ctx = context(toplevel=True)
ctx.load_compute = libcell("compute.load")

ctx.compute = macro({}, lib="compute")
ctx.load_compute.connect(ctx.compute.code)
ctx.equilibrate()

with macro_mode_on(None):
    compute = ctx.compute.ctx
    ctx.iterations = cell().set(10000)
    ctx.iterations.connect(compute.iterations)
    ctx.result = cell()
    compute.result.connect(ctx.result)

ctx.equilibrate()

compute = ctx.compute.ctx  
print(compute.readme.value)

print("START")
print(ctx.status)
print(ctx.result.value)
print(compute.result.value)
print(compute.status)
print()

lctx = context(toplevel=True)
lctx.readme = cell("text").set("Compute minus pi iteratively")
lctx.code = cell("python").set(compute_pi)
lctx.code.set(lctx.code.value.replace("return ", "return -"))
lctx.load = cell("macro").set(load)
lctx.equilibrate()
lib, root = library.build(lctx)
library.register("compute", lib, root)

ctx.equilibrate()
compute = ctx.compute.ctx
print(compute.readme.value)
print(ctx.status)
print(ctx.compute.ctx.result.value)

from seamless.core import context, cell, transformer, macro, libcell
from seamless.core import library

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
    ctx.iterations = link(ctx.tf.iterations)
    ctx.result = link(ctx.tf.pi)

lctx = context(toplevel=True)
lctx.readme = cell("text").set("Compute pi iteratively")
lctx.code = cell("python").set(compute_pi)
lctx.load = cell("macro").set(load)
lctx.equilibrate()
lib = library.build(lctx)
library.register("compute", lib)

ctx = context(toplevel=True)
ctx.load_compute = libcell("compute.load")

ctx.compute = macro({}, lib="compute")
ctx.load_compute.connect(ctx.compute.code)
compute = ctx.compute.gen_context
print(compute.readme.value)
ctx.iterations = cell().set(10000)
ctx.iterations.connect(compute.iterations)
ctx.result = cell()
print("START")
print()
compute.result.connect(ctx.result)
ctx.equilibrate()

print(ctx.status())
print(ctx.result.value)
print()

lctx = context(toplevel=True)
lctx.readme = cell("text").set("Compute minus pi iteratively")
lctx.code = cell("python").set(compute_pi)
lctx.code.set(lctx.code.value.replace("return ", "return -"))
lctx.load = cell("macro").set(load)
lctx.equilibrate()
lib = library.build(lctx)
library.register("compute", lib)

print(compute.readme.value)
ctx.equilibrate()
print(ctx.status())
print(ctx.result.value)

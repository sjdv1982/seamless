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

def compute_e(iterations):
    fact = 1
    e = 0
    for n in range(iterations):
        if n > 1:
            fact *= n
        e += 1.0/fact
    return e

def load_pi(ctx):
    ctx.tf = transformer({
        "iterations": "input",
        "pi": "output"
    })
    ctx.code = libcell(".pi.code")
    ctx.code.connect(ctx.tf.code)
    ctx.iterations = cell()
    ctx.iterations.connect(ctx.tf.iterations)
    ctx.result = cell()
    ctx.tf.pi.connect(ctx.result)

def load_e(ctx):
    ctx.tf = transformer({
        "iterations": "input",
        "e": "output"
    })
    ctx.code = libcell(".e.code")
    ctx.code.connect(ctx.tf.code)
    ctx.iterations = cell()
    ctx.iterations.connect(ctx.tf.iterations)
    ctx.result = cell()
    ctx.tf.e.connect(ctx.result)

def select(ctx, which):
    assert which in ("pi", "e"), which
    ctx.readme = libcell(".readme")
    ctx.loader = macro({})
    if which == "pi":
        ctx.load = libcell(".pi.load")
    else:
        ctx.load = libcell(".e.load")
    ctx.load.connect(ctx.loader.code)
    compute = ctx.loader.ctx
    ctx.iterations = cell()
    ctx.iterations.connect(compute.iterations)
    ctx.result = cell()
    compute.result.connect(ctx.result)

lctx = context(toplevel=True)
lctx.readme = cell("text").set("Compute pi or e iteratively")
lctx.pi = context()
lctx.pi.code = cell("python").set(compute_pi)
lctx.pi.load = cell("macro").set(load_pi)
lctx.e = context()
lctx.e.code = cell("python").set(compute_e)
lctx.e.load = cell("macro").set(load_e)
lctx.select = cell("macro").set(select)
lctx.equilibrate()
lib, root = library.build(lctx)
library.register("compute", lib, root)


select_params = {
    "which": "text",
}

def main():
    global ctx, compute
    ctx = context(toplevel=True)
    ctx.select_compute = libcell("compute.select")
    ctx.compute = macro(select_params, lib="compute")
    ctx.select_compute.connect(ctx.compute.code)
    ###ctx.compute.which.cell().set("pi") # TODO: malfunctioning
    ### KLUDGE
    ctx.which_cell = cell().set("pi")
    ctx.which_cell.connect(ctx.compute.which)
    ### /KLUDGE
    compute = ctx.compute.ctx
    ctx.iterations = cell().set(10000)
    ctx.iterations.connect(compute.iterations)
    ctx.result = cell()
    compute.result.connect(ctx.result)

with macro_mode_on():
    main()
ctx.equilibrate()    
print(ctx.status)
import sys; sys.exit()

compute = ctx.compute.ctx
print(compute.readme.value)
ctx.equilibrate()

print(ctx.status)
print(ctx.result.value)
print()

ctx.iterations.set(100)
###ctx.compute.which.cell().set("e") # TODO: malfunctioning
ctx.which_cell.set("e") # KLUDGE
ctx.equilibrate()
print(ctx.status)
print(ctx.result.value)
print()

compute = ctx.compute.ctx
print(compute.readme.value)
lctx.readme.set("test")
lib, root = library.build(lctx, root)
library.register("compute", lib, root)
print(compute.readme.value)

lctx.select.set(lctx.select.value + "    ctx.readme2 = libcell('.readme')")
lib, root = library.build(lctx)
library.register("compute", lib, root)
ctx.equilibrate()
compute = ctx.compute.ctx
print(compute.readme2.value)
print(ctx.result.value)
print()

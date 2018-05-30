#port to the high-level of the corresponding file in tests/lowlevel
# for now, just a mockup

import seamless
from seamless import Context, Cell

ctx = Context()

#the following can be wrapped in a "with ctx.atomic" (ctx.self.atomic) statement
# in which case the mid/low-level representations are not regenerated every line

ctx.inp = {"a": 10} #creates a low-level StructuredCell
ctx.inp.celltype = "json" #default: "silk". Now, "json" sets low-level .storage and .schema to None, and the Monitor becomes "plain"
#or: ctx.inp = Cell("json").set({"a": 10})
ctx.tf = ctx.inp.a + ctx.inp.b #generates code "out = a + b" and sets "out" as the target of assignment
    #by default, "a" and "b" have mode=None => ctx.inp.celltype, but here, it matters not
ctx.x = Cell("text")
ctx.result = None #creates a low-level StructuredCell
ctx.result.x = ctx.x
ctx.result.y = ctx.tf
ctx.tf2 = ctx.c + 1000
"""
#or:
def func(c):
    return c + 1000
ctx.tf2 = func
ctx.tf2.c = ctx.c #or ctx.tf2.input.c = ctx.c
#or:
code = "cc = c + 1000"
ctx.tf2 = seamless.Transformer(lang="python")
ctx.tf2.set(code) #ctx.tf2.self.set(code)
ctx.tf2.self.output_name = "cc"
ctx.tf2.self.assignment = "output" #is default?
ctx.tf2.c = ctx.c #or ctx.tf2.input.c = ctx.c
"""
ctx.z = ctx.tf2
ctx.mount("/tmp/mount-test")

#end of "with atomic"; the following lines do not cause regeneration

ctx.inp.b = 20
ctx.equilibrate()
print(ctx.result.value)

print(ctx.tf.status())
print(ctx.tf2.status())
print(ctx.z.value)

ctx.inp.b = 25
ctx.equilibrate()
print(ctx.z.value)

shell = ctx.tf.shell()

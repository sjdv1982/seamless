import seamless
seamless.delegate(False)

from seamless.workflow.core import cell, context

ctx = context(toplevel=True)
ctx.c1 = cell("int").set(12)
ctx.c1a = cell("mixed").set(12)
ctx.compute()
print(ctx.c1.value, ctx.c1.checksum)
print(ctx.c1a.value, ctx.c1a.checksum)
print()

ctx.t1 = cell("checksum")
ctx.c1.connect(ctx.t1)
ctx.t1a = cell("checksum")
ctx.c1a.connect(ctx.t1a)
ctx.tt1 = cell("int")
ctx.t1.connect(ctx.tt1)
ctx.compute()
print(ctx.t1.buffer)
print(ctx.t1.value)
print(ctx.t1a.value)
print(ctx.tt1.value, ctx.tt1.checksum)
print()

ctx.c2 = cell("mixed", hash_pattern={"*": "#"})
c2 = {
    "a": 100,
    "b": 200,
    "c": 300
}
ctx.c2.set(c2)
ctx.compute()
print(ctx.c2.value)
print(ctx.c2.data)
print(ctx.c2.checksum)
print()

ctx.t2 = cell("checksum")
ctx.c2.connect(ctx.t2)
ctx.tt2 = cell("mixed", hash_pattern={"*": "#"})
ctx.t2.connect(ctx.tt2)
ctx.compute()
print(ctx.t2.buffer)
print(ctx.t2.value)
print(ctx.t2.data)
print(ctx.tt2.value)
print()
print(ctx._get_manager().resolve(ctx.t2.value["b"], celltype="mixed"))
print(ctx.tt2.status)

ctx.t3 = cell("checksum").set({
    "blah": "aaaa9161bef6f183d0938f090fbd6ea6377e386829c032c19a318461247e813b"
})
ctx.tt3 = cell("mixed", hash_pattern={"*": "#"})
ctx.t3.connect(ctx.tt3)
ctx.compute()
print(ctx.t3.checksum, ctx.t3.buffer)
print(ctx.tt3.buffer)

from seamless.workflow.core.cache import CacheMissError
try:
    print(ctx.tt3.value)
except CacheMissError:
    import traceback
    traceback.print_exc(limit=0)
import seamless
seamless.delegate(False)

import traceback
from seamless.workflow import Context, Cell, DeepCell

ctx = Context()
ctx.a = DeepCell()
print(ctx.a)
ctx.translate()
ctx.a.set({"test": 0, "test2": 0})  # possible, but against the spirit of deep cells
ctx.a.test = 1
ctx.a.test2 = 2
ctx.compute()
print(ctx.a.status)
print(ctx.a.exception)
print(ctx.a.data)
print(ctx.a._get_context().origin.value)
ctx.a.test3.set(20)
ctx.a.test4 = 55
ctx.compute()
print(ctx.a)
print(ctx.a.data)
print(ctx.a._get_context().origin.value)
print(ctx.a.data["test2"], ctx.resolve(ctx.a.data["test2"], "mixed"))
print(ctx.a.checksum)
print(ctx.a.keyorder)
print(ctx.a.keyorder_checksum)
print(ctx.a._get_context().filtered.value)
print()
ctx.a.keyorder = ["test3", "test2", "test1"]
ctx.compute()
print(ctx.a.keyorder)
print(ctx.a.keyorder_checksum)
print()

ctx.a2 = ctx.a
print(ctx.a2)
ctx.compute()
try:
    print(ctx.a2.value)
except Exception:
    import traceback
    traceback.print_exc(0)
print(ctx.a2.data)
print(ctx.a2.checksum)
print(ctx.a2.keyorder_checksum)

ctx.a3 = DeepCell()
ctx.a3 = ctx.a
ctx.compute()
print(ctx.a3.data)
print(ctx.a3.keyorder)
ctx.a.keyorder = ["test1", "test2", "test3"]
ctx.compute()
print(ctx.a3.keyorder)

ctx.test = Cell("int")
ctx.test = ctx.a3.test4
ctx.compute()
print(ctx.test.value)

# disallowed
ctx.somecell = Cell()
try:
    ctx.somecell = ctx.a
except Exception:    
    traceback.print_exc(0)
    print()
del ctx.somecell
ctx.translate()

ctx.a.set({"test": 1, "test2": 2})
ctx.atest = ctx.a.test
ctx.atest4 = ctx.a.test4
ctx.compute()
print(ctx.a.checksum)
print(ctx.a.keyorder)
print(ctx.a.keyorder_checksum)
print(ctx.a._get_context().filtered.value)
print("test", ctx.atest.value)
print("test4", ctx.atest4.value)
print()

ctx.a.set({"test3": 10, "test4": 11})
ctx.compute()
print(ctx.a.checksum)
print(ctx.a.keyorder)
print(ctx.a.keyorder_checksum)
print(ctx.a._get_context().filtered.value)
print("test", ctx.atest.value)
print("test4", ctx.atest4.value)
print()

import seamless
seamless.delegate(False)

import traceback
from seamless.highlevel import Context, Cell, DeepFolderCell

ctx = Context()
ctx.a = DeepFolderCell()
print(ctx.a)
ctx.translate()
ctx.a.set({"test": "value"})  # possible, but against the spirit of deep cells
ctx.a.test2 = 123
ctx.compute()
print(ctx.a.data)
print(ctx.a._get_context().origin.value)
ctx.a.test3.set("20")
ctx.a.test4 = b"somebuffer"
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
print(ctx.a2.data)

ctx.a3 = DeepFolderCell()
ctx.a3 = ctx.a
ctx.compute()
print(ctx.a3.data)
print(ctx.a3.keyorder)
ctx.a.keyorder = ["test1", "test2", "test3"]
ctx.compute()
print(ctx.a3.keyorder)

ctx.test = Cell("bytes")
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
ctx.compute()

ctx.blacklist = Cell("plain")
ctx.a3.blacklist = ctx.blacklist
ctx.compute()
print(ctx.test.value)
ctx.blacklist.set(["test4"])
ctx.compute()
print(ctx.test.value)

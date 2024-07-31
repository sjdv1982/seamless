import seamless
seamless.delegate(False)

from seamless.workflow import Context, Cell, DeepCell

ctx = Context()
ctx.a = DeepCell()

ctx.a.checksum = "0" * 64
ctx.compute()
print(ctx.a.status)
print(ctx.a.exception)
ctx.a.checksum = None
ctx.compute()
print(ctx.a.status)
ctx.a.test1 = 10
ctx.a.test2 = 20
ctx.a.test3 = 30
ctx.compute()
print(ctx.a.status)
ctx.a.keyorder = "nonsense"
ctx.compute()
print(ctx.a.status)
print(ctx.a.exception)
ctx.a.keyorder = None
ctx.compute()
print(ctx.a.status)
print()
ctx.filt = ctx.a
ctx.a.whitelist = ["test1", "test3"]
ctx.compute()
print(ctx.a.data)
print(ctx.a._get_context().filtered.value)
print(ctx.filt.data)
print(ctx.filt.keyorder)
ctx.a.keyorder = ["test3", "whatever", "test1"]
ctx.compute()
print(ctx.a.keyorder)
print(ctx.filt.keyorder)
print()
ctx.whitelist = Cell("plain")
ctx.a.whitelist = ctx.whitelist
ctx.compute()
print(ctx.a.whitelist)
print(ctx.filt.data)
print()
ctx.whitelist.set(["test2", "test3"])
ctx.compute()
print(ctx.filt.data)
ctx.whitelist.set(None)
ctx.compute()
print(ctx.filt.data)
print()
ctx.blacklist = Cell("plain").set(["test2"])
ctx.a.blacklist = ctx.blacklist
ctx.blacklist.mount("/tmp/blacklist.json", authority="cell")
ctx.compute()

# assign normal cell to deep cell
ctx.filt_cell0 = Cell()
ctx.filt_cell0.hash_pattern = {"*": "#"}
ctx.filt_cell0 = ctx.filt
ctx.filt_cell = Cell("plain")
ctx.filt_cell = ctx.filt_cell0
ctx.filt_cell.mount("/tmp/filt_cell.json", "w", authority="cell")
ctx.compute()
print(ctx.filt.data)
print()
# assign deep cell to normal cell (with hash pattern)
ctx.deep2 = DeepCell()
ctx.deep2 = ctx.filt_cell0
ctx.compute()
print(ctx.deep2.data)
print()

# assign deep cell to normal cell
ctx.c = Cell("plain").set({
    "a": 10,
    "b": 20,
    "c": 30
})
ctx.deep3 = DeepCell()
ctx.deep3 = ctx.c
ctx.compute()
print(ctx.deep3.data)
print(ctx.deep3._get_context().filtered.value)
print()


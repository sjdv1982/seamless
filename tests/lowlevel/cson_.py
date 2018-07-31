import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, csoncell, textcell, jsoncell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cson = csoncell().set("""
test: "a"
test2: ["b", "c", "d"]
""")
    ctx.mount("/tmp/mount-test")
    ctx.json = jsoncell()
    ctx.cson.connect(ctx.json)

ctx.equilibrate()
print(ctx.cson.value)
assert ctx.json.value == ctx.cson.value

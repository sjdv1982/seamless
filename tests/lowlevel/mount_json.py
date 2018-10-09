import seamless
from seamless.core import macro_mode_on
from seamless.core import context,cell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.json = cell("json").set({})
    ctx.json.mount("/tmp/test.json", "w")

ctx.equilibrate()
ctx.json.set({"a": 1})

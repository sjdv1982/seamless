import seamless
from seamless.core import macro_mode_on
from seamless.core import context,cell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.json = cell("plain").set({"a": 1})
    ctx.json.mount("/tmp/test.json", authority="cell")

ctx.equilibrate()


import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, reactor, StructuredCell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell("json")
    ctx.result = cell("json")
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.tf.code.cell().set("c = min(a, b+3)")
    ctx.v_form = cell("json")
    ctx.v = StructuredCell(
        "v",
        ctx.cell1,
        storage = None,
        form = ctx.v_form,
        schema = None,
        buffer = None,
        inchannels = [("result",), ("c",)],
        outchannels = [("a",), ("c",)],
        editchannels = [("b",)],
    )
    ctx.v.connect_outchannel(("a",), ctx.tf.a)
    ctx.v.connect_outchannel(("b",), ctx.tf.b)
    ctx.v.connect_inchannel(ctx.tf.c, ("c",))
    ctx.tf.c.connect(ctx.result)

    ctx.rc = reactor({
      "result": "output",
      "b": {"io": "edit", "must_be_defined": False},
      "c": {"io": "input", "must_be_defined": False}
    })
    ctx.v.connect_inchannel(ctx.rc.result, ("result",))
    ctx.v.connect_editchannel(("b",), ctx.rc.b)
    ctx.v.connect_outchannel(("c",), ctx.rc.c)
    ctx.rc.code_start.cell().set("""
print("reactor start")
count = 0
    """)
    ctx.rc.code_update.cell().set("""
if count < 100:
    print("reactor update", count)
    count += 1
    c = PINS.c.value
    if c is None:
        c = 0
    b_pre = PINS.b.value
    if b_pre is None:
        b_pre = 0
    b = c
    print(b_pre, b, c)
    PINS.b.set(b)
    PINS.result.set(b)
    """)
    ctx.rc.code_stop.cell().set("")
    ctx.mount("/tmp/mount-test")


v = ctx.v.handle
v["a"] = 6

ctx.equilibrate()
print(ctx.result.value)

v["a"] = 24
ctx.equilibrate()
print(ctx.result.value)

v["a"] = 7
ctx.equilibrate()
print(ctx.result.value)

v["a"] = 40
ctx.equilibrate()
print(ctx.result.value)

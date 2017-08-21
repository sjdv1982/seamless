from seamless import context, cell, transformer, macro
ctx = context()

@macro("str")
def m(ctx, identifier):
    from seamless import cell, reactor
    ctx.identifier = cell("str").set(identifier)
    ctx.rc = reactor({
        "text": {"pin": "input", "dtype": "str"},
        "identifier": {"pin": "input", "dtype": "str"},
    })
    ctx.identifier.connect(ctx.rc.identifier)
    ctx.rc.code_start.cell().set("")
    ctx.rc.code_update.cell().set("print('M,', PINS.identifier.value, ',' , PINS.text.value)")
    ctx.rc.code_stop.cell().set("")
    ctx.export(ctx.rc)

ctx.text = cell("str").set("hello")
ctx.id1 = cell("str").set("first macro")
ctx.id2 = cell("str").set("second macro")
ctx.m1 = m(ctx.id1)
ctx.text.connect(ctx.m1.text)
ctx.m2 = m(ctx.id2)
ctx.text.connect(ctx.m2.text)
ctx.equilibrate()
ctx.id1.set("first macro redefined")
ctx.equilibrate()
print()
print("If the reconnection goes correctly, the first macro responds before the second:")
ctx.text.set("hello again")
ctx.equilibrate()

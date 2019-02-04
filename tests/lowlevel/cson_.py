import seamless
from seamless.core import macro_mode_on
from seamless.core import context, reactor, cell, csoncell, textcell, plaincell, pythoncell
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cson = csoncell().set("""
test: "a"
test2: ["b", "c", "d"]
""")
    ctx.json = plaincell()
    ctx.cson.connect(ctx.json)
    ctx.text = textcell()
    ctx.cson.connect(ctx.text)

    ctx.rc = reactor({
        "json": ("input", "ref", "json", "json"),
        "cson": ("input", "ref", "text", "cson"),
        "cson2": ("input", "ref", "json", "cson"),
        "text": ("input", "ref", "text", "text"),
        "silk": ("input", "ref", "silk", "json"),
    })
    ctx.json.connect(ctx.rc.json)
    ctx.cson.connect(ctx.rc.cson)
    ctx.cson.connect(ctx.rc.cson2)
    ctx.text.connect(ctx.rc.text)
    ctx.json.connect(ctx.rc.silk)
    ctx.rc.code_start.cell().set("")
    ctx.rc.code_stop.cell().set("")
    ctx.code = pythoncell().set("""
if PINS.json.updated:
    print("JSON updated")
if PINS.cson.updated:
    print("CSON text updated")
if PINS.cson2.updated:
    print("CSON JSON representation updated")
if PINS.text.updated:
    print("text updated")
print("silk test2:")
print(PINS.silk.value.test2)
print("reactor done")
""")
    ctx.code.connect(ctx.rc.code_update)
    ctx.code2 = textcell()
    ctx.code.connect(ctx.code2)
    ctx.code3 = pythoncell()
    ctx.code.connect(ctx.code3)
    ctx.mount("/tmp/mount-test")

print("START")
ctx.equilibrate()
print("")

print("REPORT")
print(ctx.cson.value)
assert ctx.json.value == ctx.cson.value
print(ctx.cson.data)
print("")

print("UPDATE")
ctx.cson.set(ctx.cson.data + " ")
ctx.equilibrate()
print("")

print("UPDATE2")
ctx.cson.set(ctx.cson.data[:-1] + "test3: 10 ")
ctx.equilibrate()
print("")
print(ctx.rc.status())

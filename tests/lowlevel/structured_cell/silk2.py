import seamless
from seamless.core.macro import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.hub_struc = context(name="hub_struc",context=ctx)
    ctx.hub_struc.data = cell("mixed")
    ctx.hub_struc.storage = cell("text")
    ctx.hub_struc.form = cell("json")
    ctx.hub_struc.schema = cell("json")
    ctx.hub_struc.buffer = cell("json")
    ctx.hub = StructuredCell(
        "hub",
        ctx.hub_struc.data,
        storage = ctx.hub_struc.storage,
        form = ctx.hub_struc.form,
        schema = ctx.hub_struc.schema,
        #buffer = ctx.hub_struc.buffer,
        inchannels = [("m1",), ("m2",)],
        outchannels = [()]
    )
    print("TODO: next line should not be necessary (Silk-specific)")
    ctx.hub.handle.set({}) ###

    ctx.code = cell("pytransformer").set("z = x * y")

    ctx.mixer1 = transformer({
        "x": "input",
        "y": "input",
        "z": "output",
    })
    ctx.a = cell("json").set(3)
    ctx.b = cell("json").set(8)
    ctx.code.connect(ctx.mixer1.code)
    ctx.a.connect(ctx.mixer1.x)
    ctx.b.connect(ctx.mixer1.y)

    ctx.mixer2 = transformer({
        "x": "input",
        "y": "input",
        "z": "output",
    })
    ctx.c = cell("json").set(2)
    ctx.d = cell("json").set(12)
    ctx.code.connect(ctx.mixer2.code)
    ctx.c.connect(ctx.mixer2.x)
    ctx.d.connect(ctx.mixer2.y)

    ctx.hub.connect_inchannel(ctx.mixer1.z, ("m1",))
    ctx.hub.connect_inchannel(ctx.mixer2.z, ("m2",))

    ctx.hub_cell = cell("json")
    ctx.hub.connect_outchannel((), ctx.hub_cell)

    ctx.result_struc = context(name="result_struc",context=ctx)
    ctx.result_struc.data = cell("mixed")
    ctx.result_struc.storage = cell("text")
    ctx.result_struc.form = cell("json")
    ctx.result_struc.schema = cell("json")
    ctx.result_struc.buffer = cell("json")
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        storage = ctx.result_struc.storage,
        form = ctx.result_struc.form,
        schema = ctx.result_struc.schema,
        #buffer = ctx.result_struc.buffer,
        inchannels = [("hub",), ("herring",)],
        outchannels = [("herring",)]
    )

    print("TODO: next line should not be necessary (it is Silk-specific)")
    ctx.result.handle.set({}) ###

    ctx.result.connect_inchannel(ctx.hub_cell, ("hub",))

    ctx.herring = cell("text").set("herring")
    ctx.result.connect_inchannel(ctx.herring, ("herring",))

    ctx.tf_herring = transformer({
        "herring": "input",
        "whatever": "output",
    })
    ctx.tf_herring.code.cell().set("""print("HERRING")
whatever = None
""")

    ctx.result.connect_outchannel(("herring",), ctx.tf_herring.herring)


ctx.equilibrate()
print(ctx.result.handle)

print("START")
hub = ctx.hub.handle

def func(self):
    assert abs(self.m1) == abs(self.m2), self

hub.add_validator(func)


print("STAGE 0")
#this will fail
try:
    hub.m1 = 16
except:
    import traceback
    traceback.print_exc()
print(ctx.result.handle)

print("STAGE 0a")
#this will succeed
with hub.fork():
    hub.m1 = 16
    hub.m2 = 16
print(ctx.result.handle)

print("STAGE 0b")
#this will succeed
with hub.fork():
    hub.m1 = 24
    hub.m2 = 24
print(ctx.result.handle)


print("STAGE 1")
#this will fail
ctx.a.set(-8)
import time; time.sleep(0.1)
ctx.b.set(3)
ctx.equilibrate()
print(ctx.result.handle)

print("STAGE 2")
#TODO: this should succeed, need buffer
ctx.a.set(5)
ctx.b.set(12)
ctx.c.set(10)
ctx.d.set(6)
ctx.equilibrate()
print(ctx.result.handle)

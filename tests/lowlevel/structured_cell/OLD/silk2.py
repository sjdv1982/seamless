import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell
from seamless.core.structured_cell import BufferWrapper
import numpy as np

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.hub_struc = context(name="hub_struc",context=ctx)
    ctx.hub_struc.storage = cell("text")
    ctx.hub_struc.form = cell("json")
    ctx.hub_struc.data = cell("mixed",
        form_cell = ctx.hub_struc.form,
        storage_cell = ctx.hub_struc.storage,
    )
    ctx.hub_struc.schema = cell("json")
    ctx.hub_struc.buffer_storage = cell("text")
    ctx.hub_struc.buffer_form = cell("json")
    ctx.hub_struc.buffer_data = cell("mixed",
        form_cell = ctx.hub_struc.buffer_form,
        storage_cell = ctx.hub_struc.buffer_storage,
    )
    bufferwrapper = BufferWrapper(
        ctx.hub_struc.buffer_data,
        ctx.hub_struc.buffer_storage,
        ctx.hub_struc.buffer_form
    )
    ctx.hub = StructuredCell(
        "hub",
        ctx.hub_struc.data,
        storage = ctx.hub_struc.storage,
        form = ctx.hub_struc.form,
        schema = ctx.hub_struc.schema,
        buffer = bufferwrapper,
        inchannels = [("m1",), ("m2",)],
        outchannels = [()]
    )

    ctx.code = cell("transformer").set("z = x * y")

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

    ctx.hub_cell = cell()
    ctx.hub.connect_outchannel((), ctx.hub_cell)

    ctx.result_struc = context(name="result_struc",context=ctx)
    ctx.result_struc.storage = cell("text")
    ctx.result_struc.form = cell("json")
    ctx.result_struc.data = cell("mixed",
        form_cell = ctx.result_struc.form,
        storage_cell = ctx.result_struc.storage,
    )
    ctx.result_struc.schema = cell("json")
    ctx.result_struc.buffer_storage = cell("text")
    ctx.result_struc.buffer_form = cell("json")
    ctx.result_struc.buffer_data = cell("mixed",
        form_cell = ctx.result_struc.buffer_form,
        storage_cell = ctx.result_struc.buffer_storage,
    )
    bufferwrapper = BufferWrapper(
        ctx.result_struc.buffer_data,
        ctx.result_struc.buffer_storage,
        ctx.result_struc.buffer_form
    )
    ctx.result = StructuredCell(
        "result",
        ctx.result_struc.data,
        storage = ctx.result_struc.storage,
        form = ctx.result_struc.form,
        schema = ctx.result_struc.schema,
        buffer = bufferwrapper,
        inchannels = [("hub",), ("herring",)],
        outchannels = [("herring",)]
    )

    ctx.result.connect_inchannel(ctx.hub_cell, ("hub",))

    ctx.herring = cell("text").set("herring!!")
    ctx.result.connect_inchannel(ctx.herring, ("herring",))

    ctx.tf_herring = transformer({
        "herring": "input",
        "whatever": "output",
    })
    ctx.tf_herring.code.cell().set("""print("HERRING", herring)
whatever = None
""")

    ctx.result.connect_outchannel(("herring",), ctx.tf_herring.herring)

    ctx.mount("/tmp/mount-test")

ctx.equilibrate()
print(ctx.result.handle)

print("START")
hub = ctx.hub.handle

dt = np.dtype([("m1", int),("m2",int)],align=True)
d = np.zeros(1,dt)[0]
ctx.hub.set(d)
print(hub)

def func(self):
    assert abs(self.m1) == abs(self.m2), self

hub.add_validator(func)

print("STAGE 0")
#this will fail
try:
    hub.m1 = 16
except Exception:
    import traceback
    traceback.print_exc()
print(ctx.hub.value, ctx.hub.handle)
ctx.equilibrate()
print(ctx.result.handle)
hub.m1 = 24 ##restore

print("STAGE 0a")
#this will succeed
with hub.fork():
    hub.m1 = 16
    hub.m2 = 16
ctx.equilibrate()
print(ctx.result.value)

print("STAGE 0b")
#this will succeed
with hub.fork():
    hub.m1 = 24
    hub.m2 = 24
print(ctx.result.value)

print("STAGE 1")
#this will fail (but will be repaired)
ctx.a.set(-8)
ctx.equilibrate()
print(hub, ctx.hub.value)
ctx.b.set(3)
ctx.equilibrate()
print(hub, ctx.hub.value)
print(ctx.result.value)


print("STAGE 2")
#this will fail (but will be repaired)
hub.m1 = 80
ctx.equilibrate()
print(hub, ctx.hub.value)
print(ctx.result.value)
print("set m2...")
hub.m2 = 80
ctx.equilibrate()
print(ctx.hub_cell.value)
print(ctx.result.value)


print("STAGE 2a")
#this will fail (but will be repaired)
ctx.a.set(5)
ctx.b.set(12)
ctx.c.set(10)
ctx.d.set(6)
ctx.equilibrate()
print(ctx.result.value)

#ctx.herring.set("herring123")

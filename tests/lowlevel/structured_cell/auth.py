import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, StructuredCell
from seamless.core.structured_cell import BufferWrapper, StructuredCellState
import numpy as np

with macro_mode_on():
    ctx = context(toplevel=True)

def create(ctx, mount, state=None):
    with macro_mode_on():
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
            inchannels = [("a", "factor1"), ("a", "factor2"), ("b",)],
            outchannels = [("a",), ("b",), ("c",)],
            state = state,
        )

        ctx.code = cell("transformer").set("d = a.factor1 * b + a.factor2 * c + a.constant")

        ctx.mixer = transformer({
            "a": ("input", "ref", "silk"),
            "b": ("input", "ref", "object"),
            "c": ("input", "ref", "object"),
            "d": ("output", "ref", "json"),
        })
        ctx.a_factor1 = cell("json")
        ctx.a_factor2 = cell("json")
        ctx.b = cell("json")
        ctx.code.connect(ctx.mixer.code)

        ctx.hub.connect_inchannel(ctx.a_factor1, ("a", "factor1"))
        ctx.hub.connect_inchannel(ctx.a_factor2, ("a", "factor2"))
        ctx.hub.connect_inchannel(ctx.b, ("b",))

        ctx.hub.connect_outchannel(("a",), ctx.mixer.a)
        ctx.hub.connect_outchannel(("b",), ctx.mixer.b)
        ctx.hub.connect_outchannel(("c",), ctx.mixer.c)

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
            inchannels = [()],
            outchannels = []
        )

        ctx.result.connect_inchannel(ctx.mixer.d, ())
        if mount:
            ctx.mount("/tmp/mount-test")


create(ctx, mount=False)
ctx.a_factor1.set(3)
ctx.a_factor2.set(4)
ctx.b.set(5)


print("START")
hub = ctx.hub.handle
print(hub)

hub.a.constant = 2
hub.c = 6
print(hub)
print(ctx.hub.value)

ctx.equilibrate()
print("RESULT", ctx.result.value)

print(ctx.status())
#import sys; sys.exit()

def func(self):
    assert self.b < self.c, self
    assert self.a.constant > 0, self
hub.add_validator(func)

print("START 2")
hub.a.constant = -6
hub.c = 10
print(hub)
print(ctx.hub.value)

ctx.equilibrate()
print(ctx.result.value)

state = StructuredCellState()
state.set(ctx.hub)

print("state storage", state.storage)
print("state data", state.data)
print("state form", state.form)
print("state schema", state.schema)
print("state buffer storage", state.buffer_storage)
print("state buffer data", state.buffer_data)
print("state buffer form", state.buffer_form)

ctx.destroy()
del ctx

with macro_mode_on():
    ctx = context(toplevel=True)
create(ctx, mount=False, state=state)
ctx.a_factor1.set(23)
ctx.a_factor2.set(24)
ctx.b.set(1)

ctx.equilibrate()
print("RESULT2", ctx.result.value)
print(ctx.result.value)
hub = ctx.hub.handle
print(hub)
print(ctx.hub.value)
print()

hub.a.constant = 2
hub.c = 6
print(hub)
print(ctx.hub.value)

ctx.equilibrate()
print("RESULT3", ctx.result.value)

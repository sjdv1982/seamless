raise NotImplementedError ###

import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, macro, libcell, StructuredCell
from seamless.core.structured_cell import BufferWrapper, StructuredCellState
from seamless.core import library

with macro_mode_on():
    ctx = context(toplevel=True)

def create(ctx, with_buffer, with_schema, inchannels):
    with macro_mode_on():
        ctx.struc = context(name="struc",context=ctx)
        ctx.struc.storage = cell("text")
        ctx.struc.form = cell("json")
        ctx.struc.data = cell("mixed",
            form_cell = ctx.struc.form,
            storage_cell = ctx.struc.storage,
        )
        schema = None
        if with_schema:
            ctx.struc.schema = cell("json")
            schema = ctx.struc.schema
        bufferwrapper = None
        if with_buffer:
            ctx.struc.buffer_storage = cell("text")
            ctx.struc.buffer_form = cell("json")
            ctx.struc.buffer_data = cell("mixed",
                form_cell = ctx.struc.buffer_form,
                storage_cell = ctx.struc.buffer_storage,
            )
            bufferwrapper = BufferWrapper(
                ctx.struc.buffer_data,
                ctx.struc.buffer_storage,
                ctx.struc.buffer_form
            )
        ctx.hub = StructuredCell(
            "hub",
            ctx.struc.data,
            storage = ctx.struc.storage,
            form = ctx.struc.form,
            schema = schema,
            buffer = bufferwrapper,
            inchannels = inchannels,
            outchannels = [],
        )


def load(ctx):
    ctx.readme = libcell(".readme")
    def recreate(ctx, name0, with_buffer, with_schema, inchannels):
        name = "." + name0
        ctx.struc = context(name="struc",context=ctx)
        ctx.struc.storage = libcell(name+".storage")
        ctx.struc.form = libcell(name+".form")
        ctx.struc.data = libmixedcell(name+".data",
            form_cell = ctx.struc.form,
            storage_cell = ctx.struc.storage,
        )
        schema = None
        if with_schema:
            ctx.struc.schema = libcell(name+".schema")
            schema = ctx.struc.schema
        bufferwrapper = None
        if with_buffer:
            ctx.struc.buffer_storage = libcell(name+".buffer_storage")
            ctx.struc.buffer_form = libcell(name+".buffer_form")
            ctx.struc.buffer_data = libmixedcell(name+".buffer_data",
                form_cell = ctx.struc.buffer_form,
                storage_cell = ctx.struc.buffer_storage,
            )
            bufferwrapper = BufferWrapper(
                ctx.struc.buffer_data,
                ctx.struc.buffer_storage,
                ctx.struc.buffer_form
            )
        ctx.hub = StructuredCell(
            "hub",
            ctx.struc.data,
            storage = ctx.struc.storage,
            form = ctx.struc.form,
            schema = schema,
            buffer = bufferwrapper,
            inchannels = inchannels,
            outchannels = [],
        )
    ctx.auth_json = context(name="auth_json", context=ctx)
    recreate(ctx.auth_json, "auth_json.struc", with_buffer=False, with_schema=False, inchannels=[])
    ctx.auth = context(name="auth", context=ctx)
    recreate(ctx.auth, "auth.struc", with_buffer=False, with_schema=True, inchannels=[])
    ctx.err = context(name="err", context=ctx)
    recreate(ctx.err, "err.struc", with_buffer=True, with_schema=True, inchannels=[])
    ctx.nauth = context(name="nauth", context=ctx)
    try:
        recreate(ctx.nauth, "nauth.struc", with_buffer=False, with_schema=False, inchannels=[("z",)])
    except Exception:
        import traceback; traceback.print_exc()

with macro_mode_on():
    ctx.readme = cell().set("readme")
    ctx.load = cell("macro").set(load)

    ctx.auth_json = context(name="auth_json", context=ctx)
    create(ctx.auth_json, with_buffer=False, with_schema=False, inchannels=[])
    auth_json = ctx.auth_json.hub
    auth_json.set("value of auth_json")

    ctx.auth = context(name="auth", context=ctx)
    create(ctx.auth, with_buffer=False, with_schema=True, inchannels=[])
    auth = ctx.auth.hub
    auth.handle.a = "value of auth.a"
    auth.handle.b = "value of auth.b"
    print(auth.value)
    def val(self):
        assert isinstance(self.a, str)
        assert isinstance(self.b, str)
    auth.handle.add_validator(val)
    print(auth.handle.schema)

    ctx.err = context(name="err", context=ctx)
    create(ctx.err, with_buffer=True, with_schema=True, inchannels=[])
    err = ctx.err.hub
    err.handle.a = "value of err.a"
    err.handle.b = "value of err.b"
    def val(self):
        assert isinstance(self.a, str)
        assert isinstance(self.b, str)
    err.handle.add_validator(val)
    err.handle.b = 20
    print(err.value)
    print(err.handle.schema)

    ctx.nauth = context(name="nauth", context=ctx)
    create(ctx.nauth, with_buffer=False, with_schema=False, inchannels=[("z",)])
    nauth = ctx.nauth.hub
    nauth.handle["a"] = "value of nauth.a"
    nauth.handle["b"] = "value of nauth.b"
    print(nauth.value)

lib = library.build(ctx)
library.register("test", lib)
print()

print("!" * 80)
print("LOAD")
print("!" * 80)
ctx2 = context(toplevel=True)
ctx2.load_test = libcell("test.load")
ctx2.test = macro({}, lib="test")
ctx2.load_test.connect(ctx2.test.code)
test = ctx2.test.gen_context
print(test.readme.value)

print("!" * 80)
print("INIT")
print("!" * 80)
auth_json = test.auth_json.hub
print(auth_json.value)
auth = test.auth.hub
print(auth.value, auth.schema.value)
err = test.err.hub
print("VALUE", err.value, "HANDLE", err.handle, err.schema.value)

ctx.auth.hub.handle.a.set("updated value of auth")
ctx.err.hub.handle.b = "fixed"
ctx.equilibrate()
lib = library.build(ctx)
library.register("test", lib)

print("!" * 80)
print("UPDATED")
print("!" * 80)
auth_json = test.auth_json.hub
print(auth_json.value)
auth = test.auth.hub
print(auth.value, auth.schema.value)
err = test.err.hub
print("VALUE", err.value, "HANDLE", err.handle, err.schema.value)

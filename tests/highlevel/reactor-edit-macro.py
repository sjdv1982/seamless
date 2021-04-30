from seamless.highlevel import Context, Macro, Cell
ctx = Context()
m = ctx.m = Macro()
m.pins.x = {"io": "input", "celltype": "int"}
m.pins.y = {"io": "input", "celltype": "int"}
m.pins.z = {"io": "edit", "celltype": "int", "must_be_defined": False}
def run_macro(ctx):
    ctx.x = cell("int")
    ctx.y = cell("int")
    ctx.z = cell("int")
    ctx.rc = reactor({
        "a": "input",
        "b": "input",
        "c": {"io": "edit", "must_be_defined": False},
    })
    ctx.x.connect(ctx.rc.a)
    ctx.y.connect(ctx.rc.b)
    ctx.code_start = cell("python").set("")
    ctx.code_start.connect(ctx.rc.code_start)
    ctx.code_update = cell("python").set("""
if PINS.a.updated or PINS.b.updated:
    a = PINS.a.get()
    b = PINS.b.get()
    PINS.c.set(a+b)
    """)
    ctx.code_update.connect(ctx.rc.code_update)
    ctx.code_stop = cell("python").set("")
    ctx.code_stop.connect(ctx.rc.code_stop)
    ctx.rc.c.connect(ctx.z)

m.code = run_macro
ctx.p = 2
ctx.q = 3
ctx.r = Cell("int")
m.x = ctx.p
m.y = ctx.q
m.z = ctx.r
ctx.compute()
print("START 1")
print(ctx.m.exception)
print(ctx.m.ctx.status)
print(ctx.m.ctx.x.status)
print(ctx.m.ctx.x.value)
print(ctx.m.ctx.y.value)
print(ctx.m.ctx.z.value)
print(ctx.m._get_mctx().z.value)
print(ctx.r.value)
print("START 2")
ctx.p = 7
ctx.compute()
print(ctx.r.value)
print("START 3")
ctx.r = 99
ctx.compute()
print(ctx.r.value)
print("START 4")
ctx.p = 8
ctx.compute()
print(ctx.r.value)

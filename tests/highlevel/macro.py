from seamless.highlevel import Context, Macro
ctx = Context()
m = ctx.m = Macro()
ctx.a = 10
m.a = ctx.a
m.b = 20
m.pins.x = {"io": "input", "celltype": "int"}
m.pins.y = {"io": "output", "celltype": "int"}
def run_macro(ctx, a, b):
    pins = {
        "a": "input", 
        "b": "input",
        "x": "input",
        "y": "output",
    }
    ctx.tf = transformer(pins)
    ctx.tf.a.cell().set(a)
    ctx.tf.b.cell().set(b)
    ctx.x = cell("int")
    ctx.x.connect(ctx.tf.x)
    ctx.tf.code.cell().set("y = a * b + x")
    ctx.y = cell("int")
    ctx.tf.y.connect(ctx.y)
    
m.code = run_macro
"""
ctx.compute()
#print(m.exception)
#print(m._get_node())
print(ctx.m._get_mctx().macro.ctx.x.value)
print(ctx.m._get_mctx().macro.ctx.tf.status)
"""
ctx.x = 2
m.x = ctx.x
ctx.compute()
print(ctx.m._get_mctx().macro.status)
print(ctx.m._get_mctx().macro.exception)
print(ctx.m._get_mctx().macro.ctx.x.value)

lg = ctx._manager.livegraph
x = ctx.m._get_mctx().x
print(x.value)
x2 = ctx.m._get_mctx().macro.ctx.x
print(x2.value)
mpath = lg.cell_to_downstream[x][0].write_accessor.target()
print(mpath, mpath._cell)
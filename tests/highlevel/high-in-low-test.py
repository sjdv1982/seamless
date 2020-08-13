from seamless.highlevel import Context, Cell, Macro

ctx = Context()
ctx.a = Cell("int")
ctx.b = Cell("int").set(20)
def add(a,b):
    return a+b
ctx.add = add
ctx.add.a = ctx.a
ctx.add.b = ctx.b
ctx.result = ctx.add
ctx.result.celltype = "int"
ctx.compute()
graph = ctx.get_graph()

ctx = Context()
ctx.graph = Cell("plain").set(graph)
m = ctx.m = Macro()
ctx.par_static = 100
ctx.par_dynamic = 20
m.par_static = ctx.par_static
m.graph = ctx.graph
m.pins.par_dynamic = {"io": "input", "celltype": "int"}
m.pins.graph_result = {"io": "output", "celltype": "int"}
def run_macro(ctx, par_static, graph):

    for node in graph["nodes"]:
        node["path"] = tuple(node["path"])
    for con in graph["connections"]:
        if con["type"] == "connection":
            con["source"] = tuple(con["source"])
            con["target"] = tuple(con["target"])
        elif con["type"] == "link":
            con["first"] = tuple(con["first"])
            con["second"] = tuple(con["second"])

    from seamless.midlevel.translate import translate
    print("RUN MACRO", par_static)
    ctx.par_dynamic = cell("int")
    ctx.subctx = context()
    translate(graph, ctx.subctx)
    ctx.subctx.a.set(par_static)

m.code = run_macro
ctx.compute()
print(ctx.m.ctx.par_dynamic)
print(ctx.m.ctx.subctx.b)
print(ctx.m.ctx.subctx.b.value)

from seamless.highlevel.assign import _assign_context
_assign_context(ctx, graph["nodes"], graph["connections"], ctx.m.ctx.subctx.path, runtime=True)

from seamless.highlevel.synth_context import SynthContext
subctx = SynthContext(ctx, ctx.m.ctx.subctx.path)
print(subctx.a, subctx.a.value)
print(subctx.b, subctx.b.value)
print(subctx.add, subctx.add.result.value)
print(subctx.result, subctx.result.value)

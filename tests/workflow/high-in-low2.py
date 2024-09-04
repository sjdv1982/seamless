import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell, Macro

ctx = Context()
ctx.a = Cell("int")
ctx.b = Cell("int")


def add(a, b):
    return a + b


ctx.add = add
ctx.add.a = ctx.a
ctx.add.b = ctx.b
ctx.result = ctx.add
ctx.result.celltype = "int"
ctx.compute()
graph = ctx.get_graph(runtime=True)

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
    print("RUN MACRO", par_static)
    ctx.subctx = HighLevelContext(graph)
    ctx.subctx.a.set(par_static)
    ctx.par_dynamic = cell("int")
    ctx.par_dynamic.connect(ctx.subctx.b)


m.code = run_macro
ctx.m.par_dynamic = ctx.par_dynamic
ctx.compute()
print(ctx.m.exception)
print(ctx.m.ctx.par_dynamic)
print(ctx.m.ctx.subctx)
print(ctx.m.ctx.subctx.a)
print(ctx.m.ctx.subctx.a.value)
print(ctx.m.ctx.subctx.b)
print(ctx.m.ctx.subctx.b.value)

subctx = ctx.m.ctx.subctx
print(subctx.a, subctx.a.value)
print(subctx.b, subctx.b.value)
print(subctx.add, subctx.add.result.value)
print(subctx.result, subctx.result.value)
print()

print("Stage 2")
ctx.par_static = 200
ctx.compute()
print(ctx.m.ctx.subctx.a)
print(ctx.m.ctx.subctx.a.value)
print(ctx.m.ctx.subctx.b)
print(ctx.m.ctx.subctx.b.value)

subctx = ctx.m.ctx.subctx
print(subctx.a, subctx.a.value)
print(subctx.b, subctx.b.value)
print(subctx.add, subctx.add.result.value)
print(subctx.result, subctx.result.value)
print()

print("Stage 3")
ctx.par_dynamic.set(21)
ctx.compute()
print(ctx.m.ctx.subctx.a)
print(ctx.m.ctx.subctx.a.value)
print(ctx.m.ctx.subctx.b)
print(ctx.m.ctx.subctx.b.value)

subctx = ctx.m.ctx.subctx
print(subctx.a, subctx.a.value)
print(subctx.b, subctx.b.value)
print(subctx.add, subctx.add.result.value)
print(subctx.result, subctx.result.value)

print()
from pprint import pprint

pprint(list(ctx._runtime_graph.nodes.keys()))

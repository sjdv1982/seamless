import seamless

seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
ctx.a = {}
ctx.translate()
ctx.a.b = {}
ctx.a.b.c = {}
ctx.a.b.c.d = 10
ctx.compute()
print(ctx.a.value)


def report(a, **args):
    print("report", a, args)


ctx.report = report
ctx.report.debug.direct_print = True
ctx.report.a = ctx.a
ctx.report.b = ctx.a.b
ctx.report.c = ctx.a.b.c
ctx.report.d = ctx.a.b.c.d
ctx.compute()
print()
ctx.a.example = ctx.a.value
ctx.compute()
ctx.a.example.b = ctx.a.b.value
ctx.compute()
ctx.a.example.b.c = ctx.a.b.c.value
ctx.compute()
ctx.a.example.b.c.d = ctx.a.b.c.d.value
ctx.compute()
print("SCHEMA A", ctx.a.schema)
print("SCHEMA B", ctx.a.schema.properties.b)
print("SCHEMA C", ctx.a.schema.properties.b.properties.c)
print("SCHEMA D", ctx.a.schema.properties.b.properties.c.properties.d)

ctx.a.schema.properties.b.properties.pop("c")
ctx.compute()
print("SCHEMA A2", ctx.a.schema)
ctx.a.b.c = None
ctx.compute()
print(ctx.report.status)
ctx.a.b.c.set({"d": 12, "dd": 22})
ctx.compute()
print(ctx.report.status)
ctx.a.b.c.d = 999
ctx.compute()
print(ctx.report.status)

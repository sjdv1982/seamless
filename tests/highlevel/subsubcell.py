from seamless.highlevel import Context
ctx = Context()
ctx.a = {}
ctx.a.b = {}
ctx.a.b.c = {}
ctx.a.b.c.d = 10
print(ctx.a.value)
def report(a,**args):
    print("report", a, args)
ctx.report = report
ctx.report.a = ctx.a
ctx.report.b = ctx.a.b
ctx.report.c = ctx.a.b.c
ctx.report.d = ctx.a.b.c.d
ctx.equilibrate()
print()
ctx.a.example = ctx.a.value
ctx.a.example.b = ctx.a.b.value
ctx.a.example.b.c = ctx.a.b.c.value
ctx.a.example.b.c.d = ctx.a.b.c.d.value
print("SCHEMA A", ctx.a.schema)
print("SCHEMA B",ctx.a.schema.properties.b)

"""
# not yet working well...
ctx.a.schema.properties.b.properties.pop("c")
print("SCHEMA A2",ctx.a.schema)

ctx.a.b.c = None
ctx.equilibrate()
print(ctx.report.status)
ctx.a.b.c = {"d": 10, "dd": 20}
ctx.equilibrate()
"""

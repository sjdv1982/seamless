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
ctx.a.schema["b"].pop("c")
ctx.a.b.c = None
ctx.equilibrate()
print(ctx.report.status())
ctx.a.b.c = {"d": 10, "dd": 20}
ctx.equilibrate()

from seamless.workflow import Context, Cell

ctx = Context()
ctx.transform = lambda a, b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.translate()
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.compute()
print(ctx.result.value)

ctx.transform.language = "cpp"
ctx.code = ctx.transform.code.pull()
ctx.code = """
extern "C" int transform(int a, int b, double *result) {
    *result = a + b + 1000;
    return 0;
}"""
ctx.translate()
ctx.transform.result.example = 0.0  # example, just to fill the schema
ctx.compute()
print(ctx.result.value)

ctx.a = 10
ctx.a.celltype = "plain"
ctx.transform.a = ctx.a

ctx.b = 30
ctx.b.celltype = "plain"
ctx.transform.b = ctx.b

ctx.transform.main_module.link_options = ["-lstdc++"]

ctx.compute()
print(ctx.result.value)
print(ctx.transform.status)
exc = ctx.transform.exception
if exc is not None:
    print(exc)

ctx.transform.debug.attach = False
ctx.transform.debug.enable("sandbox")
ctx.a = 11
ctx.compute()
ctx.transform.debug.pull()
ctx.compute()

print(ctx.transform.result.value)

ctx.transform.debug.attach = True
print("START 2")
ctx.a = 12
ctx.compute()
ctx.transform.debug.pull()
ctx.compute()

print(ctx.transform.result.value)

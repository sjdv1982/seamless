import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()
ctx.transform = lambda a,b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.equilibrate()
print(ctx.result.value)

ctx.transform.language = "cpp"
ctx.code >> ctx.transform.code
ctx.code = """
extern "C" double transform(int a, int b) {
    return a + b;
}"""
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.equilibrate()
print(ctx.result.value)

ctx.a = 10
ctx.a.celltype = "plain"
ctx.transform.a = ctx.a

ctx.b = 30
ctx.b.celltype = "plain"
ctx.transform.b = ctx.b

ctx.equilibrate()
print(ctx.result.value)
print(ctx.transform.status)
exc = ctx.transform.exception
if exc is not None:
    print(exc)

ctx.a.mount("/tmp/a.txt")
ctx.b.mount("/tmp/b.txt")
ctx.code.mount("/tmp/code.cpp")
ctx.translate()
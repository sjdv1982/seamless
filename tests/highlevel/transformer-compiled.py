import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()
ctx.mount(os.path.join(tempfile.gettempdir(), "transformer-compiled"))

ctx.transform = lambda a,b: a + b
ctx.transform.a = 0 #example, just to fill the schema
ctx.transform.b = 0 #example, just to fill the schema
ctx.result = ctx.transform
ctx.result.celltype = "json"
ctx.equilibrate()
print(ctx.result.value)

ctx.transform.language = "cpp"
ctx.code >> ctx.transform.code
ctx.code = """
extern "C" double transform(int a, int b) {
    return a + b;
}"""
ctx.transform.result = 0.0 #example, just to fill the schema
ctx.equilibrate()
print(ctx.result.value)

ctx.a = 10
ctx.a.celltype = "json"
ctx.transform.a = ctx.a

ctx.b = 30
ctx.b.celltype = "json"
ctx.transform.b = ctx.b

ctx.equilibrate()
print(ctx.result.value)
print(ctx.status())

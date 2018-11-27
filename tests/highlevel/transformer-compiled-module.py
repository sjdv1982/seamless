import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()

ctx.a = 10
ctx.a.celltype = "json"

ctx.b = 30
ctx.b.celltype = "json"

def build_transformer():
    ctx.transform = lambda a,b: a + b
    ctx.transform.example.a = 0
    ctx.transform.example.b = 0
    ctx.result = ctx.transform
    ctx.result.celltype = "json"

    ctx.transform.a = ctx.a
    ctx.transform.b = ctx.b

    ctx.transform.language = "cpp"
    ctx.transform.main_module.compiler_verbose = False
    ctx.code >> ctx.transform.code
    ctx.code = """
    extern "C" double add(int a, int b);
    extern "C" double transform(int a, int b) {
        return add(a,b);
    }"""
    ctx.transform.result.example = 0.0 #example, just to fill the schema

    ctx.transform.main_module.add.language = "c"
    code = """
    double add(int a, int b) {return a+b;};
    """
    ctx.add_code >> ctx.transform.main_module.add.code
    ctx.add_code.set(code)

build_transformer()
ctx.equilibrate()
print(ctx.result.value)

########################

build_transformer()
ctx.equilibrate()
print(ctx.result.value)

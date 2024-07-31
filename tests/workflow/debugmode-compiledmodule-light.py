import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()

ctx.a = 10
ctx.a.celltype = "plain"

ctx.b = 30
ctx.b.celltype = "plain"

def build_transformer():
    del ctx.transform
    ctx.transform = lambda a,b: a + b
    ctx.translate()
    ctx.transform.example.a = 0
    ctx.transform.example.b = 0
    ctx.result = ctx.transform
    ctx.result.celltype = "plain"

    ctx.transform.a = ctx.a
    ctx.transform.b = ctx.b

    ctx.transform.language = "cpp"
    ctx.transform.main_module.compiler_verbose = False
    ctx.code = ctx.transform.code.pull()
    ctx.code = """
    extern "C" double add(int a, int b);
    extern "C" int transform(int a, int b, double *result) {
        *result = add(a,b);
        return 0;
    }"""
    ctx.code.mount("debugmount/compiled_module/main.cpp", authority="cell")
    ctx.translate()
    ctx.transform.result.example = 0.0 #example, just to fill the schema

    ctx.transform.main_module.add.language = "c"
    code = """
double add(int a, int b) {
    return a+b;
};
    """
    ctx.add_code = Cell("code")
    ctx.add_code.language = "c"
    ctx.add_code.mount("debugmount/compiled_module/add.c", authority="cell")
    ctx.transform.main_module.add.code = ctx.add_code
    ctx.add_code.set(code)
    ctx.translate()

build_transformer()
ctx.compute()
print(ctx.result.value)

ctx.transform.debug.enable("light")
ctx.a = 100
ctx.compute()
print(ctx.result.value)

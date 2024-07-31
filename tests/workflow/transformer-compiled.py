import seamless

import os
if "DELEGATE" in os.environ:
    has_err = seamless.delegate()
    if has_err:
        exit(1)
else:
    seamless.delegate(False)

from seamless.workflow import Context

ctx = Context()
ctx.transform = lambda a,b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.translate()
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.compute()
###print(ctx.transform.get_transformation_checksum())
print(ctx.result.value)
exc = ctx.transform.exception
if exc is not None:
    print(exc)

ctx.transform.language = "cpp"
ctx.code = ctx.transform.code.pull()
ctx.code = """
extern "C" int transform(int a, int b, double *result) {
    *result = a + b;
    return 0;
}"""
ctx.translate()
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.compute()
print(ctx.result.value)
exc = ctx.transform.exception
if exc is not None:
    print(exc)

ctx.a = 10
ctx.a.celltype = "plain"
ctx.transform.a = ctx.a

ctx.b = 30
ctx.b.celltype = "plain"
ctx.transform.b = ctx.b

ctx.transform.main_module.link_options = ["-lstdc++"]
#ctx.transform.main_module.compiler_verbose = True
#ctx.transform.main_module.compiler_verbose = False

ctx.compute()
print(ctx.result.value)
print(ctx.transform.status)
exc = ctx.transform.exception
if exc is not None:
    print(exc)

ctx.a.mount("/tmp/a.txt")
ctx.b.mount("/tmp/b.txt")
ctx.result.mount("/tmp/result.txt", mode="w")
ctx.code.mount("/tmp/code.cpp")
ctx.compute()

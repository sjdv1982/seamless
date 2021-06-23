import os, tempfile
from seamless.highlevel import Context, Cell

import json

ctx = Context()
###ctx.mount(os.path.join(tempfile.gettempdir(), "transformer-compiled")) ##not working for now

ctx.transform = lambda a,b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.translate()
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.transform.language = "cpp"
ctx.compute()
print(ctx.transform.exception)
print("*" * 80)
print(ctx.transform.header.value)
print("*" * 80)
ctx.code = ctx.transform.code.pull()
ctx.code = """
extern "C" int transform(int a, int b, double *result) {
    *result = a + b;
    return 0;
}"""
ctx.compute()
print(ctx.result.value)
print(ctx.status)
print(ctx.transform.exception)

del ctx.transform  # required!
                   # else, the following line
                   # will try to re-use the existing transformer
ctx.transform = lambda a,b: a + b
ctx.transform.a = 12
ctx.transform.b = 13
ctx.result = ctx.transform
ctx.compute()
print(ctx.result.value)

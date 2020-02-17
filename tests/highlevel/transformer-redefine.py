import os, tempfile
from seamless.highlevel import Context, Cell

import json

ctx = Context()
###ctx.mount(os.path.join(tempfile.gettempdir(), "transformer-compiled")) ##not working for now

ctx.transform = lambda a,b: a + b
ctx.transform.a = 2
ctx.transform.b = 3
ctx.transform.example.a = 0
ctx.transform.example.b = 0
ctx.result = ctx.transform
ctx.result.celltype = "plain"
ctx.transform.result.example = 0.0 #example, just to fill the schema
ctx.transform.language = "cpp"
ctx.compute()
print("*" * 80)
print(ctx.transform.header.value)
print("*" * 80)
ctx.code >> ctx.transform.code
ctx.code = """
extern "C" double transform(int a, int b) {
    return a + b;
}"""
ctx.compute()
print(ctx.result.value)

ctx.transform = lambda a,b: a + b
ctx.transform.a = 12
ctx.transform.b = 13
ctx.result = ctx.transform
ctx.compute()
print(ctx.result.value)


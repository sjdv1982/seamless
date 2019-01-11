import os, tempfile
from seamless.highlevel import Context, Cell

ctx = Context()
ctx.mount(os.path.join(tempfile.gettempdir(), "transformer-compiled"))

ctx.transform = lambda a,b: a + b
ctx.transform.example.a = 0
ctx.transform.example.b = 0
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
ctx.transform.result.example = 0.0 #example, just to fill the schema
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

"""
### The code generator itself  (gen_header, translator)
 can be hacked, but in only one way:

    from seamless.highlevel import stdlib
    t = stdlib.compiled_transformer
    t.gen_header.code.mount("/tmp/gen-header.py")

This will affect all transformers.
But: by default, "t.register_library()" must be invoked upon every change.
This is a design decision that can be overruled by specifying:
    t.auto_register(True)

See the documentation of highlevel/Library.py for more details.
"""

ctx.transform.debug = True

code = """
#include <cmath>

extern "C" float add(int a, int b){
    return a + b + M_PI;
}
"""
module = {
    "objects": {
        "main": {
            "code": code,
            "language": "cpp",
        },
    },
    "link_options" : ["-lm"],
    "public_header": {
        "language": "c",
        "code": "float add(int a, int b);"
    }
}

from seamless.core import context, cell, transformer, macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.module_storage = cell("text")
    ctx.module_form = cell("plain")
    ctx.module = cell("mixed", form_cell=ctx.module_form, storage_cell=ctx.module_storage)
    ctx.module.set(binary_module, auto_form=True)
    tf = ctx.tf = transformer({
        "a": ("input", "ref", "plain"),
        "b": ("input", "ref", "plain"),
        "testmodule": ("input", "module"),
        "result": ("output", "ref", "plain"),
    })
    ctx.module.connect(tf.testmodule)
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set("""
from .testmodule import lib
print("ADD", lib.add(a,b))
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.equilibrate()
print(ctx.result.value)

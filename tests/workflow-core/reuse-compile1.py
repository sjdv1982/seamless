import seamless

seamless.delegate(level=0, force_database=True)

code = """
#include <cmath>

extern "C" float add(int a, int b){
    return a + b + M_PI;
}
"""
testmodule = {
    "type": "compiled",
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
    ctx.testmodule = cell("plain")
    ctx.testmodule.set(testmodule)
    tf = ctx.tf = transformer({
        "a": ("input", "plain"),
        "b": ("input", "plain"),
        "testmodule": ("input", "plain", "module"),
        "result": ("output", "plain"),
    })
    ctx.testmodule.connect(tf.testmodule)
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set("""
from .testmodule import lib
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.compute()
print(ctx.result.value)
ctx.save_vault("./reuse-vault")
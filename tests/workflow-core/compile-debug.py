code = """
#include <cmath>

extern "C" float addfunc(int a, int b){
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
    "target": "debug",
    "link_options": ["-lm"],
    "public_header": {"language": "c", "code": "float addfunc(int a, int b);"},
}

from seamless.workflow.core import context, cell, transformer, macro_mode_on

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.testmodule = cell("plain")
    ctx.testmodule.set(testmodule)
    tf = ctx.tf = transformer(
        {
            "a": ("input", "plain"),
            "b": ("input", "plain"),
            "testmodule": ("input", "plain", "module"),
            "result": ("output", "plain"),
        }
    )
    ctx.testmodule.connect(tf.testmodule)
    ctx.tf._debug = {
        "mode": "light",
        "direct_print": True,
        "attach": True,
        "generic_attach": True,
        "name": "Seamless .tf",
    }
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set(
        """
from .testmodule import lib
print("ADD", lib.addfunc(a,b))
result = testmodule.lib.addfunc(a,b)
    """
    )
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.compute()

from seamless.core.build_module import build_module

######################################################################
# 1: set up compiled module
######################################################################

code = """
#include <cmath>

extern "C" float add(int a, int b){
    return a + b + M_PI;
}
"""
module = {
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

######################################################################
# 2: compile it to binary module
######################################################################

from seamless.compiler import compilers, languages
testmodule = build_module(
    module, module_error_name=None,
    compilers=compilers,
    languages=languages,
    module_debug_mounts=None
)[1].lib
print(testmodule.add(2,3))

######################################################################
# 3: test it in a context
######################################################################

import seamless
import os
if "DELEGATE" in os.environ:
    has_err = seamless.delegate()
    if has_err:
        exit(1)
    from seamless.core.cache.buffer_cache import buffer_cache
    buffer_cache.buffer_cache.clear()
else:
    seamless.delegate(False)

from seamless.core import context, cell, transformer, macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.testmodule = cell("plain")
    ctx.testmodule.set(module)
    tf = ctx.tf = transformer({
        "a": ("input", "plain"),
        "b": ("input", "plain"),
        "testmodule": ("input", "plain", "module"),
        "result": ("output", "plain"),
    })
    ctx.testmodule.connect(tf.testmodule)
    tf._debug = {
        "direct_print" : True
    }
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set("""
from .testmodule import lib
print("ADD", lib.add(a,b))
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.compute()
print(ctx.result.value)
print(ctx.status)
print(tf.exception)
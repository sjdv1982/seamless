from seamless.compiler import compile
from seamless.compiler.cffi import cffi
from seamless.compiler.build_extension import build_extension_cffi

# Run with IPython/Jupyter!

######################################################################
# 1: set up compiled module
######################################################################

code = """
#include <cmath>

extern "C" float addfunc(int a, int b){
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
    "target": "debug",
    "link_options" : ["-lm"],
    "public_header": {
        "language": "c",
        "code": "float addfunc(int a, int b);"
    }
}

######################################################################
# 2: compile it to binary module
######################################################################

compiler_verbose = True
import tempfile, os
tempdir = tempfile.gettempdir() + os.sep + "compile"
binary_module = compile(module, tempdir, compiler_verbose=compiler_verbose)

######################################################################
# 3: build and test extension directly
######################################################################

module_name = build_extension_cffi(binary_module, compiler_verbose=compiler_verbose)
import sys
testmodule = sys.modules[module_name].lib
print(testmodule.addfunc(2,3))

######################################################################
# 4: test the mixed serialization protocol on the binary module
######################################################################

from seamless.mixed.get_form import get_form
from seamless.mixed.io import to_stream, from_stream
from seamless.mixed.io.util import is_identical_debug

storage, form = get_form(binary_module)
x = to_stream(binary_module, storage, form)
binary_module2 = from_stream(x, storage, form)

assert (is_identical_debug(binary_module, binary_module2))

######################################################################
# 5: test it in a debugging context
######################################################################

print("START")

from seamless.core import context, cell, transformer, macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.module_storage = cell("text")
    ctx.module_form = cell("json")
    ctx.module = cell("mixed", form_cell=ctx.module_form, storage_cell=ctx.module_storage)
    ctx.module.set(binary_module, auto_form=True)
    tf = ctx.tf = transformer({
        "a": ("input", "ref", "json"),
        "b": ("input", "ref", "json"),
        "testmodule": ("input", "ref", "binary_module"),
        "result": ("output", "ref", "json"),
    })
    ctx.tf.debug = True
    ctx.module.connect(tf.testmodule)
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set("""
from .testmodule import lib
print("ADD", lib.addfunc(a,b))
result = testmodule.lib.addfunc(a,b)
    """)
    ctx.result = cell("json")
    ctx.tf.result.connect(ctx.result)

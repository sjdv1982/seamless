from seamless.core.build_module import build_module

######################################################################
# 1: set up compiled module
######################################################################

code = """
function add(a, b) result(r) bind(C)
    use iso_c_binding
    implicit none
    integer(c_int), VALUE:: a, b
    real(c_float) r
    r = a + b
end function
"""
module = {
    #"target": "debug",
    "type": "compiled",
    "objects": {
        "main": {
            "code": code,
            "language": "f90",
        },
    },
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
    languages=languages
)[1].lib
print(testmodule.add(2,3))

######################################################################
# 3: test it in a context
######################################################################

from seamless.core import context, cell, transformer, macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.module = cell("plain")
    ctx.module.set(module)
    tf = ctx.tf = transformer({
        "a": ("input", "plain"),
        "b": ("input", "plain"),
        "testmodule": ("input", "plain", "module"),
        "result": ("output", "plain"),
    })
    ctx.tf._debug = {
        "direct_print" : True
    }
    ctx.module.connect(tf.testmodule)
    tf.a.cell().set(12)
    tf.b.cell().set(13)
    tf.code.cell().set("""
from .testmodule import lib
print("ADD", lib.add(a,b))
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.compute()
print(ctx.result.value)

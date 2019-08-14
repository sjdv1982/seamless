# run scripts/build-module-slave.py 
import os
os.environ["SEAMLESS_COMMUNION_ID"] = "compile-fortran-build-module-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
from seamless import communionserver

communionserver.configure_master(
    build_module=True,
)

redis_cache = seamless.RedisCache()

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

ctx.equilibrate()
print(ctx.result.value)

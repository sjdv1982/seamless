# run scripts/jobslave-noredis.py 

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "compile-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
seamless.set_ncores(0)
from seamless import communionserver

communionserver.configure_master(
    value=True,
    transformer_job=True,
)
communionserver.configure_servant(
    value=True,
)

from seamless.core import context, cell, transformer, macro_mode_on
with macro_mode_on():
    ctx = context(toplevel=True)
communionserver.wait(2)

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


with macro_mode_on():
    ctx.testmodule = cell("plain")
    ctx.testmodule.set(testmodule)
    tf = ctx.tf = transformer({
        "a": ("input", "ref", "plain"),
        "b": ("input", "ref", "plain"),
        "testmodule": ("input", "module"),
        "result": ("output", "ref", "plain"),
    })
    ctx.testmodule.connect(tf.testmodule)
    tf.a.cell().set(2)
    tf.b.cell().set(3)
    tf.code.cell().set("""
from .testmodule import lib
print("ADD", lib.add(a,b))
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

communionserver.wait(2)
ctx.equilibrate()
print(ctx.result.value)

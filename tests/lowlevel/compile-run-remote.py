# run scripts/jobslave-nodatabase.py

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "compile-run-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
seamless.set_ncores(0)
from seamless import communion_server

communion_server.configure_master(
    buffer=True,
    transformation_job=True,
    transformation_status=True,
)
communion_server.configure_servant(
    buffer=True,
)


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
print("ADD", lib.add(a,b))
result = testmodule.lib.add(a,b)
    """)
    ctx.result = cell("plain")
    ctx.tf.result.connect(ctx.result)

ctx.compute()
print(ctx.result.value)

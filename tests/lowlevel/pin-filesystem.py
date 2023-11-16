import seamless
from seamless.core import context, cell, transformer, macro, reactor, path
from seamless.core import macro_mode_on

import seamless
from requests import ConnectionError

try:
    seamless.delegate(level=3)
    print("Database found")
except ConnectionError:
    print("Database not found")

d1 = "/tmp/PIN-FILESYSTEM-FOLDER1"
d2 = "/tmp/PIN-FILESYSTEM-FOLDER2"

import os
from seamless.core.mount_directory import deep_read_from_directory, write_to_directory
if not os.path.exists(d1):
    write_to_directory(d1, {"file1.txt": 2}, cleanup=False, deep=False, text_only=False)    
if not os.path.exists(d2):
    write_to_directory(d2, {"file2.txt": 3}, cleanup=False, deep=False, text_only=False)


def tf_code(a, b, c, d):
    print(FILESYSTEM)
    print("pin A", a)
    print("pin B", b)
    print("pin C", c)
    print("pin D", d)
    return "OK"

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.a = cell("plain").set([1,2,3])
    ctx.b = cell("mixed")
    ctx.b._hash_pattern = {"*": "##"}
    ctx.c = cell("int").set(3.0)
    ctx.d = cell("mixed")
    ctx.d._hash_pattern = {"*": "##"}
    ctx.code = cell("str").set("CODE")
    ctx.tf_code = cell("transformer").set(tf_code)
    ctx.result = cell("str")
    ctx.tf = transformer({
        "a": {
            "io": "input",
            "filesystem": {
                "mode": "file",
                "optional": True
            }
        },
        "b": {
            "io": "input",
            "hash_pattern": {"*": "##"},
            "filesystem": {
                "mode": "directory",
                "optional": True
            }
        },
        "c": {
            "io": "input",
            "filesystem": {
                "mode": "file",
                "optional": False
            }
        },
        "d": {
            "io": "input",
            "hash_pattern": {"*": "##"},
            "filesystem": {
                "mode": "directory",
                "optional": False
            }
        },
        "result": "output"
    })
    ctx.a.connect(ctx.tf.a)
    ctx.b.connect(ctx.tf.b)
    ctx.c.connect(ctx.tf.c)
    ctx.d.connect(ctx.tf.d)
    ctx.tf_code.connect(ctx.tf.code)
    ctx.tf.result.connect(ctx.result)

ctx.compute()
deep_read_from_directory(d1, ctx.b, text_only=False, cache_buffers=True)
deep_read_from_directory(d2, ctx.d, text_only=False, cache_buffers=True)
ctx.compute()    
print("A", ctx.a.checksum, ctx.a.buffer)
print("B", ctx.b.checksum, ctx.b.buffer)
print("C", ctx.c.checksum, ctx.c.buffer)
print("D", ctx.d.checksum, ctx.d.buffer)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.logs)
print(ctx.result.checksum)
print(ctx.result.value)
print(ctx.tf.get_transformation_checksum())

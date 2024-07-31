import seamless
seamless.delegate(False)

import shutil
shutil.rmtree("/tmp/mount-test1",ignore_errors=True)
shutil.rmtree("/tmp/mount-test2",ignore_errors=True)
shutil.rmtree("/tmp/mount-test3",ignore_errors=True)
shutil.rmtree("/tmp/mount-test4",ignore_errors=True)
shutil.rmtree("/tmp/mount-test5",ignore_errors=True)

from seamless.workflow.core import context, cell, macro_mode_on

print("Write, no deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed")
    ctx.c.set({
        "a": "Value A",
        "b": [3,4,5],
        "c": "Value C"
    })
    ctx.c.mount("/tmp/mount-test1", mode="w", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Read, no deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed")
    ctx.c.mount("/tmp/mount-test1", mode="r", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Write from raw strings, no deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed")
    ctx.c.set({'a': 'Value A\n', 'b': '[\n  3,\n  4,\n  5\n]\n', 'c': 'Value C\n'})
    ctx.c.mount("/tmp/mount-test2", mode="w", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Re-read, no deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed")
    ctx.c.mount("/tmp/mount-test2", mode="r", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Write, deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.set({
        "a": "Value A",
        "b": [3,4,5],
        "c": "Value C"
    })
    ctx.c.mount("/tmp/mount-test3", mode="w", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Read, deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.mount("/tmp/mount-test3", mode="r", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Write from raw strings, deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.set({'a': 'Value A\n', 'b': '[\n  3,\n  4,\n  5\n]\n', 'c': 'Value C\n'})
    ctx.c.mount("/tmp/mount-test4", mode="w", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

print("Re-read, deepfolder")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.mount("/tmp/mount-test4", mode="r", as_directory=True)

ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

import numpy as np
print("Write, raw bytes")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.set({
        'sub/p': b'UTF-8 encodable value', 
        'sub/q': np.arange(20), 
        'sub/r': np.arange(120, 130).astype(np.uint8).tobytes(), 
    })
    ctx.c.mount("/tmp/mount-test5", mode="w", as_directory=True)
ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()

ctx.destroy()

import os
os.system("openssl dgst -sha3-256 /tmp/mount-test5/sub/q")

print("Re-read, raw bytes")
with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"##"})
    ctx.c.mount("/tmp/mount-test5", mode="r", as_directory=True)
ctx.compute()
print(ctx.c.value)
print(ctx.c.checksum)
print()
print(ctx.c.data["sub/q"])



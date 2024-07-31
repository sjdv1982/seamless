import seamless
seamless.delegate(False)

import os
import numpy as np
from seamless.workflow import Context, FolderCell
os.system("""
rm -rf /tmp/foldercell
mkdir /tmp/foldercell
""")
np.save("/tmp/foldercell/a.npy", np.arange(2,12) )
with open("/tmp/foldercell/x.txt", "w") as f:
    f.write(""" This is a test
    where text
is written.    
""")

ctx = Context()
ctx.fc = FolderCell()
ctx.fc.mount("/tmp/foldercell", "r")
ctx.compute()
print(ctx.fc.value)

def func(fc):
    print(fc)
    return 42
ctx.tf = func
ctx.tf.fc = ctx.fc
ctx.compute()
print()
print("pin celltype:", ctx.tf.pins.fc.celltype)
print()
# Note the difference between FolderCell.value
#  and the value of a "folder" pin inside a transformer
print(ctx.tf.logs)

ctx.tf.fc.celltype = "mixed"
ctx.compute()
print()
print("pin celltype:", ctx.tf.pins.fc.celltype)
print()
print(ctx.tf.logs)

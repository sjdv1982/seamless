import seamless
seamless.delegate(False)

from seamless.workflow import Context, FolderCell
import numpy as np
import shutil
ctx = Context()
f = ctx.folder = FolderCell()
shutil.rmtree("./testfolder", ignore_errors=True)
f.mount("./testfolder",mode="w")
ctx.compute()
f["test.txt"] = "This is a\ntest"
f["test.dat"] = b"Test buffer"
f["test.json"] = {"a":10, "b":20, "c":30}
f["test.npy"] = np.arange(10)
f["test2.dat"] = np.arange(130).tobytes()
f["sub/test2.txt"] = "And another\ntest"
f["sub/test3.npy"] = np.arange(10,20)
ctx.compute()
print(f.data)
print(ctx.resolve(f.data["test.txt"]))
print(ctx.resolve(f.data["test.txt"], "text"))
print()
print(ctx.resolve(f.data["test.json"]))
print(ctx.resolve(f.data["test.json"], "plain"))
print()
value = f._get_cell().value.unsilk
print(value["test.dat"], type(value["test.dat"]))
print(value["test.txt"], type(value["test.txt"]))
print(value["test.json"], type(value["test.json"]))
print(value["test.npy"], type(value["test.npy"]))
print(value["test2.dat"][:20], type(value["test2.dat"]))
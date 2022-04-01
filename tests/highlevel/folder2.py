from seamless.highlevel import Context, FolderCell, Cell
ctx = Context()
f = ctx.folder = FolderCell()
f.mount("./testfolder",mode="r")
ctx.compute()
print(f.data)
print(f.checksum)

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
try:
    f["gives-error.txt"] = "Error"
except AttributeError:
    import traceback
    traceback.print_exc(limit=0)

print("STAGE 2")
ctx.folder2 = ctx.folder
print(ctx.folder2)
exit(0)

ctx.cell = Cell()
ctx.cell = ctx.folder
ctx.compute()
print(ctx.cell.status)
print(ctx.cell.exception)
value = ctx.cell.value.unsilk
print(value["test.dat"], type(value["test.dat"]))
print(value["test.txt"], type(value["test.txt"]))
print(value["test.json"], type(value["test.json"]))
print(value["test.npy"], type(value["test.npy"]))
print(value["test2.dat"].tobytes()[:20], type(value["test2.dat"]))

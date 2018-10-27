from seamless.highlevel import Context
ctx = Context()
ctx.txt = "not OK"
ctx.txt.celltype = "text"
ctx.txt.mount("mount.txt", authority="file")
ctx.equilibrate()
print(ctx.txt.value)

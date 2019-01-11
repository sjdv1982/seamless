import seamless
f = "test-editor-lib.seamless"
f2 = "test-editor-lib-reload.seamless"
ctx = seamless.fromfile(f)

ctx.equilibrate()
ctx.tofile(f2, backup=False)

ctx.destroy() ##should not be necessary, but it is, for now (hard ref somewhere)
ctx = seamless.fromfile(f2)
print(ctx.c_data.value)
print(ctx.c_output.value) #None with python3, 15 or None with ipython3
ctx.equilibrate()
print(ctx.c_data.value)
print(ctx.c_output.value) #always 15

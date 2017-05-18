import seamless
from seamless import context, cell, transformer
from seamless.lib.filelink import link
ctx = context()
ctx.value = cell("int")
ctx.result = cell("int")
#ctx.result.resource.save_policy = 4 #always save value
ctx.result.resource.save_policy = 2 #always save hash
ctx.tf = transformer({
    "value": {
        "pin": "input",
        "dtype": "int"
    },
    "result": {
        "pin": "output",
        "dtype": "int"
    },
})
ctx.tf.code.cell().set("""print("evaluate!"); return value""")
ctx.value.connect(ctx.tf.value)
ctx.tf.result.connect(ctx.result)
ctx.value.set(42)
ctx.link_value = link(ctx.value, ".", "hashcache-value.txt")
ctx.link_result = link(ctx.result, ".", "hashcache-result.txt", file_dominant=True)
ctx.equilibrate()
ctx.tofile("test-hashcache.seamless",backup=False)
ctx = seamless.fromfile("test-hashcache.seamless")
ctx.equilibrate()
print(ctx.result.value)
print("LOAD 1")
ctx.destroy()
ctx = seamless.fromfile("test-hashcache.seamless")
ctx.equilibrate()
print(ctx.result.value) #42, and no "evaluate!""
print("Changing result to 99...")
ctx.destroy()
open("hashcache-result.txt", "w").write("99")
print("LOAD 2")
ctx = seamless.fromfile("test-hashcache.seamless")
print(ctx.result.value) #usually 99, sometimes 42
ctx.equilibrate()
print(ctx.result.value) #42

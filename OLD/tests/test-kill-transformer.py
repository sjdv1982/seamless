import seamless
from seamless import cell, transformer
ctx = seamless.context()
ctx.count = cell("int").set(10)
ctx.tf = transformer({
    "count": {"pin": "input", "dtype": "int"}
})
ctx.count.connect(ctx.tf.count)
ctx.tf.code.cell().set("""
import time
for n in range(count):
    print(n+1)
    time.sleep(0.5)
return
""")
ctx.equilibrate(2)
ctx.count.set(20)
ctx.equilibrate(2)

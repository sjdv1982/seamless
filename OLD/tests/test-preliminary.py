"""
Careful with this feature:
  for now, ALL pins react on preliminary cell values, which is definitely NOT
    what you want for e.g. JSON or python cells
  In the future, inputpins will have to be specifically declared to support
   preliminary cell values
"""
import seamless
from seamless import context, cell, transformer
ctx = context()
ctx.value = cell("int")
ctx.value.resource.save_policy = 4 #always save cell value
tf = ctx.tf = transformer({
    "pulses": {"pin": "input", "dtype": "int"},
    "delay": {"pin": "input", "dtype": "float"},
    "value": {"pin": "output", "dtype": "int"},
})
tf.value.connect(ctx.value)
tf.code.cell().set("""
import time
for n in range(pulses):
    return_preliminary(n)
    time.sleep(delay)
return pulses
""")
ctx.delay = cell("float").set(0.1)
ctx.delay.connect(tf.delay)
ctx.pulses = cell("int").set(3)
ctx.pulses.connect(tf.pulses)

reporter = ctx.reporter = transformer({"value": {"pin": "input", "dtype": "int"}})
ctx.value.connect(reporter.value)
reporter.code.cell().set("""
print("VALUE", value)
return None
"""
)
ctx.equilibrate(0.29) ##time enough for 2 pulse delays, but not enough for completion
print("PRELIMINARY?", ctx.value._preliminary, ctx.value.value) #True, 2
ctx.tofile("test-preliminary-1.seamless", backup=False) #ctx.value must be empty
ctx.equilibrate()
print("PRELIMINARY?", ctx.value._preliminary, ctx.value.value) #False, 3
ctx.tofile("test-preliminary-2.seamless", backup=False) #ctx.value must be 3

from seamless.lib import edit, display
ctx.delay.set(0.5)
ctx.pulses.set(10)
edit(ctx.pulses, "Pulses")
edit(ctx.delay, "Delay")
display(ctx.value, "Value")

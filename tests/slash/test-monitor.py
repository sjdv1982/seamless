from seamless import context, cell, transformer
from seamless.lib import display, edit, link
from seamless.slash import slash0
import time

code = """
@input_doc pulse_py
@input_var pulses
@input_var delay
@intern count
@intern value
python3 !pulse_py $pulses $delay > count
tail -1 !count > value
@export value
"""

ctx = context()
ctx.pre_code = cell(("text", "code", "slash-0")).set(code)
gen_code = ctx.gen_code = transformer({
    "in_code": {"pin": "input", "dtype": ("text", "code", "slash-0")},
    "monitor": {"pin": "input", "dtype": "bool"},
    "out_code": {"pin": "output", "dtype": ("text", "code", "slash-0")},
})
gen_code.monitor.set(False)
gen_code.code.set("""
if not monitor:
    return in_code
lines = []
for l in in_code.splitlines():
    if l.find("python3 !pulse_py") > -1:
        l += " @monitor 0.01"
    lines.append(l)
return "\\n".join(lines)
""")
ctx.pre_code.connect(gen_code.in_code)
ctx.code = gen_code.out_code.cell()

ctx.printer = transformer({"value": {"pin":"input", "dtype": "int"}})
ctx.printer.code.set("print('VALUE', value); return")

ctx.equilibrate()
p = ctx.slash0 = slash0(ctx.code)
ctx.value = cell("int")
p.value.connect(ctx.value)
ctx.value.connect(ctx.printer.value)
ctx.pulse_py = cell(("text", "code", "python"))
ctx.pulse_py.connect(p.pulse_py)
ctx.pulses = cell("int").set(3)
ctx.pulses.connect(p.pulses)
ctx.delay = cell("float").set(0.1)
ctx.delay.connect(p.delay)
link(ctx.pulse_py, ".", "pulse.py")
ctx.equilibrate()
print("... DONE", ctx.value.value)
gen_code.monitor.set(True)
ctx.equilibrate()
print("... DONE", ctx.value.value)


ctx.delay.set(0.5)
ctx.pulses.set(10)
edit(ctx.pulses, "Pulses")
edit(ctx.delay, "Delay")
display(ctx.value, "Value")

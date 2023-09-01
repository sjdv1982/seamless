import sys
import seamless
from_vault = bool(int(sys.argv[1]))
if from_vault:
    seamless.load_vault(sys.argv[2])
from requests import ConnectionError
try:
    seamless.config.database.connect()
    print("Database found")
except ConnectionError:
    print("Database not found")

from seamless.highlevel import Context, Macro
ctx = Context()
m = ctx.m = Macro()
m.pins.a = {"io": "input", "celltype": "int"}
m.pins.c = {"io": "output", "celltype": "int"}
ctx.a = 10
m.a = ctx.a
m.b = 20
def run_macro(ctx, b):
    print("RUN MACRO", b)
    pins = {
        "a": "input",
        "b": "input",
        "c": "output",
    }
    ctx.tf = transformer(pins)
    ctx.tf._debug = {"direct_print": True}
    ctx.a = cell("int")
    ctx.a.connect(ctx.tf.a)
    ctx.tf.b.cell().set(b)
    ctx.tf.code.cell().set("""
print('RUN TRANSFORMER', a, b)
c = a * b  + 1000""")
    ctx.c = cell("int")
    ctx.tf.c.connect(ctx.c)
    return
m.code = run_macro
ctx.result = ctx.m.c
m.elision = True
ctx.compute()
print(ctx.result.value)
print(m.status, m.exception)

if not from_vault:
    ctx.save_vault(sys.argv[2])
import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell
import traceback

ctx = Context()
ctx.a = Cell("int").set(20)
ctx.b = ctx.a
ctx.b.celltype = "int"
ctx.compute()
print(ctx.b.value)
try:
    ctx.b.mount("/tmp/x")
except Exception:
    traceback.print_exc()
try:
    ctx.b.share(readonly=False)
except Exception:
    traceback.print_exc()
ctx.compute()

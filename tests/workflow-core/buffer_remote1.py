import seamless
seamless.delegate(level=2)
from seamless.workflow.core import context, cell

ctx = context(toplevel=True)
ctx.a = cell("mixed").set_checksum("31e9824583b780a3f5a3548ca3e94af0d6bd135c51523a6215c8dd76e99556a6")
ctx.b = cell("mixed").set_checksum("57127eeb621b1871dafb0c14d612658417a11539a72e186d9681194f2929681b")
ctx.c = cell("mixed").set_checksum("f676fe8c51ddc3bcd33228cbbcfca60195c0618fb3bfaccd24c1b6dc266e6acc")

ctx.compute()
print(ctx.a.value, ctx.b.value, ctx.c.value)
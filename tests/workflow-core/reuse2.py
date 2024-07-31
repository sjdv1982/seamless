import seamless
seamless.delegate(False)
from seamless.workflow.core import context, cell

ctx = context(toplevel=True)
seamless.vault.load_vault("./reuse-vault")

ctx.a = cell().set_checksum("bc4bb29ce739b5d97007946aa4fdb987012c647b506732f11653c5059631cd3d")
ctx.b = cell().set_checksum("191fb5fc4a9bf2ded9a09a0a2c4eb3eb90f15ee96deb1eec1a970df0a79d09ba")
ctx.result = cell().set_checksum("f9bfa088acf25803b123d3251fe4bf6e3dcd8fa1d3eac07d2e4275f5aa3b540a")
ctx.compute()
print(ctx.a.value)
print(ctx.b.value)
print(ctx.result.value)
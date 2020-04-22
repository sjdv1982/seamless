import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, unilink
from seamless import get_hash

seamless.set_ncores(0)
from seamless import communion_server
communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

#redis_cache = seamless.RedisCache()

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(2)
    ctx.cell2 = cell().set(3)
    ctx.result = cell()
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer")    
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

ctx.code.set_checksum("f71eba57962891040561f1379572d97d6eb29ee7be4f95aac01e3ba697d74010")
print("Secret source code", ctx.code.checksum)

print()
print("START RESULT CACHE")
print()

ctx.compute()

print(ctx.status)
print(ctx.result.checksum)
print(ctx.result.value)

print()
print("START COMPUTATION")
print()

ctx.cell1.set(4)
ctx.compute()

print(ctx.status)
print(ctx.result.value)

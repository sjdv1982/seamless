import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer, pytransformercell, link
from seamless import get_hash

seamless.set_ncores(0)
from seamless import communion_server
communion_server.configure_master(
    value=True, 
    transformer_job=True,
    transformer_result=True,
    transformer_result_level2=True
)
communion_server.configure_servant(value=True)

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
    ctx.code = pytransformercell()    
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)

raise NotImplementedError # no more labels; use checksum literal
###ctx.code.from_label("Secret source code")
print("Secret source code", ctx.code.checksum)

ctx.equilibrate()
print(ctx.status)
print(ctx.result.checksum)
print(ctx.result.value)

communion_server.configure_master(value=False)
with macro_mode_on():
    ctx.cell1.set(100)
    ctx.cell2.set(200)

ctx.equilibrate()
print(ctx.status)
communion_server.configure_master(value=True)
print(ctx.result.value)

communion_server.configure_master(value=False)
with macro_mode_on():
    ctx.cell1.set(3)
    ctx.cell2.set(200)

ctx.equilibrate()
print(ctx.status)
communion_server.configure_master(value=True)
print(ctx.result.value)

communion_server.configure_master(value=False)
print(ctx.code.value)  # Should raise Exception, unless ctx.code.value has been fetched previously

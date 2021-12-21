from seamless.core import context, cell, macro_mode_on

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.c = cell("mixed", hash_pattern={"*":"#"})
    ctx.c.set({
        "a": "Value a",
        "b": [3,4,5],
        "c": "Value C"
    })
    #ctx.c.mount("/tmp/mount-test", as_directory=True, authority="cell")

ctx.compute()
print(ctx.c.value)
print(ctx.c.data)
from seamless import context, macro, cell

@macro("int", with_context=False)
def add_all(inputs):
    from seamless import transformer
    pattern = "inp"
    params = {
        "outp": {"pin": "output", "dtype": "int"}
    }
    code = "return "
    for n in range(inputs):
        p = pattern + str(n+1)
        params[p] = {"pin": "input", "dtype": "int"}
        code += p + "+ "
    code = code[:-2]
    t = transformer(params)
    t.code.cell().set(code)
    return t

ctx = context()
ctx.c1 = cell("int").set(1)
ctx.c2 = cell("int").set(2)
ctx.t1 = add_all(ctx.c1)
ctx.t2 = add_all(ctx.c2)
ctx.t1.inp1.cell().set(10)
ctx.t2.inp1.cell().set(20)
ctx.t2.inp2.cell().set(30)

#from seamless.lib.gui.basic_editor import edit
#ctx.ed1 = edit(ctx.t1.outp.cell(),solid=False)
#ctx.ed2 = edit(ctx.t2.outp.cell(),solid=False)

code2 = ctx.t1.macro.macro.code.replace('"inp"', '"INP"')
ctx.t1.macro.macro.update_code(code2)
print(ctx.t2.INP2)

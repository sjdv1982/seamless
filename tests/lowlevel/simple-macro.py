from seamless.core import macro_mode, context, cell, macro

ctx = context(toplevel=True)
ctx.macro = macro({
    "a": "ref",
})
ctx.a = cell().set(42)

def code(ctx, a):
    ctx.answer = cell().set(a)
    ctx.double = transformer({"test": "input", "result": "output"})
    ctx.answer.connect(ctx.double.test)
    ctx.double.code.cell().set("test * 2")
    ctx.result = cell()
    ctx.double.result.connect(ctx.result)

ctx.code = cell("macro").set(code)
ctx.a.connect(ctx.macro.a)
ctx.code.connect(ctx.macro.code)
ctx.equilibrate()
print(ctx.macro.ctx.answer.value)
print(ctx.macro.ctx.result.value)
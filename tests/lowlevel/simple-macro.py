from seamless.core import macro_mode, context, cell, macro

with macro_mode.macro_mode_on(None):
    ctx = context(toplevel=True)
    ctx.mount("/tmp/test-mount-macro")

ctx.macro = macro({
    "a": "mixed",
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
print(ctx.macro.status)
print(ctx.macro.ctx.answer.value)
print(ctx.macro.ctx.result.value)
ctx.result0 = cell() 
ctx.macro.ctx.result.connect(ctx.result0)
ctx.equilibrate()
print(ctx.result0.value)
print("Update...")
ctx.a.set(5)
ctx.equilibrate()
print(ctx.macro.ctx.answer.value)
print(ctx.macro.ctx.result.value)
print(ctx.result0.value)
ctx.macro.ctx.result.connect(ctx.result0)
ctx.equilibrate()
print(ctx.result0.value)

print("Update 2 ...")
ctx.a.set(6)
ctx.equilibrate()
print(ctx.macro.ctx.result.value)
print(ctx.result0.value)

print("Update 2a ...")
with macro_mode.macro_mode_on(None):
    ctx.macro.ctx.result.connect(ctx.result0)
ctx.equilibrate()
print(ctx.result0.value)

print("Update 3 ...")
ctx.a.set(7)
ctx.equilibrate()
print(ctx.macro.ctx.result.value)
print(ctx.result0.value)

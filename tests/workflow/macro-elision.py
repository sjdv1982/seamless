import seamless
seamless.delegate(False)

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
    ctx.a = cell("int")
    ctx.a.connect(ctx.tf.a)
    ctx.tf.b.cell().set(b)
    ctx.tf.code.cell().set("c = a * b")
    ctx.c = cell("int")
    ctx.tf.c.connect(ctx.c)
    return
m.code = run_macro
ctx.result = ctx.m.c
ctx.compute()
print(ctx.result.value)
print(m.status, m.exception)
print("re-translate")
m.elision = True
ctx.translate(force=True)
ctx.compute()  # Must NOT print RUN MACRO, because of elision
print(ctx.result.value)
print(m.status, m.exception)
print("change b to 10")
ctx.m.b = 10
ctx.compute()  # Must print RUN MACRO 10
print(ctx.result.value)  # 100
print(m.status, m.exception)
print("change b back to 20")
ctx.m.b = 20
ctx.compute()  # Must NOT print RUN MACRO 20, because of elision
print(ctx.result.value)  # 200
print(m.status, m.exception)
print("change a to 8")
ctx.a = 8
ctx.compute()  # Must print RUN MACRO 20, because elision is broken
print(ctx.result.value)  # 160
print(m.status, m.exception)
print("change a back to 10")
ctx.a = 10
ctx.compute()  # Must NOT print RUN MACRO 20, because elision is restored
print(ctx.result.value)
print(m.status, m.exception)
print("change a again to 8")
ctx.a = 8
ctx.compute()  # Must NOT print RUN MACRO 10, because of elision
print(ctx.result.value)  # 160
print(m.status, m.exception)

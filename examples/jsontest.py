from seamless import cell, context, transformer, time
ctx = context()
typ = ("json", "seamless", "transformer_params")
#typ = "json"
c = ctx.c = cell(typ).set({"test":10})
t = ctx.t = transformer({
"input":{"pin": "input", "dtype": typ},
"value":{"pin": "output", "dtype": "int"},
}
)
t.code.cell().set("""return input['test']""")
c.connect(t.input)
x = t.value.cell()
time.sleep(0.001)
print('X',x.data)

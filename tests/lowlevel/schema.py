import seamless
from seamless.core import macro_mode_on
from seamless.core import context, cell, transformer
from silk.meta import meta

class MyClass(metaclass=meta):
    def get(self, item):
        if item == 1:
            return self.f1
        elif item == 2:
            return self.f2
        else:
            raise IndexError(item)

schema = MyClass.schema

with macro_mode_on():
    ctx = context(toplevel=True)
    ctx.cell1 = cell().set(1)
    ctx.cell2 = cell().set(2)
    ctx.result = cell("plain")
    ctx.tf = transformer({
        "a": "input",
        "b": "input",
        "f": ("input", "silk"),
        "f_SCHEMA": "input",
        "c": "output"
    })
    ctx.cell1.connect(ctx.tf.a)
    ctx.cell2.connect(ctx.tf.b)
    ctx.code = cell("transformer").set("c = a + b")
    ctx.code.connect(ctx.tf.code)
    ctx.tf.c.connect(ctx.result)
    ctx.f = cell("plain").set({"f1": 10, "f2": 20})
    ctx.f.connect(ctx.tf.f)
    ctx.f_schema = cell("plain").set(schema)
    ctx.f_schema.connect(ctx.tf.f_SCHEMA)

ctx.compute()
print(ctx.result.value)
ctx.cell1.set(10)
ctx.compute()
print(ctx.result.value)
ctx.code.set("""
c = a * f.get(1) + b * f.get(2)
""")
ctx.compute()
print(ctx.result.value)
print(ctx.status)
print(ctx.f.value)

#shell = ctx.tf.shell()

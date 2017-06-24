from seamless import context, cell, pythoncell, reactor

ctx = context()
ctx.code = pythoncell().set("""
class MyClass:
    def __init__(self, a, b, c):
        self.a = a
        self.b = b
        self.c = c
    def __str__(self):
        return "MyClass: {0} {1} {2}".format(self.a, self.b, self.c)
""")
ctx.registrar.python.register(ctx.code)
rc = ctx.rc = reactor({})
ctx.registrar.python.connect("MyClass", rc)
rc.code_start.cell().set("print( MyClass(1,2,3) )")
rc.code_update.cell().set("")
rc.code_stop.cell().set("")

from seamless import context, cell, pythoncell, reactor, transformer

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
ro = ctx.registrar.python.register(ctx.code)

# Repeated registration
v = ctx.code.value
#ctx.code.destroy() # Should not be necessary
#ro.destroy() # Should not be necessary
ctx.code = pythoncell().set(v)
ctx.registrar.python.register(ctx.code)
ctx.equilibrate()

rc = ctx.rc = reactor({})
ctx.registrar.python.connect("MyClass", rc)
rc.code_start.cell().set("print( 'start', MyClass(1,2,3) )")
rc.code_update.cell().set("print( 'update', MyClass(1,2,3) )")
rc.code_stop.cell().set("print('stop')")

tf = ctx.tf = transformer({})
ctx.registrar.python.connect("MyClass", tf)
tf.code.cell().set("print( 'transform', MyClass(1,2,3) ); return")

ctx.equilibrate()
ctx.code.set(ctx.code.value + " ")
ctx.equilibrate()

#TODO: more complicated graph, run gc, etc.

from seamless import context
ctx = context()
silkmodel = """Type Foo {
  Integer x
  Integer y
}"""

ctx.registrar.silk.register(silkmodel)
ctx.destroy()

ctx2 = context()
ctx2.registrar.silk.register(silkmodel)

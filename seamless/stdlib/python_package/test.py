from seamless.highlevel import Context, Cell, Module, Transformer
from seamless.highlevel import set_resource

ctx = Context()

mod = ctx.analyze_dependencies = Module()
mod.code = set_resource("analyze_dependencies.py")
tf = ctx.build_package = Transformer()
tf.code = set_resource("build_package.py")
ctx.package_dirdict = Cell("plain")
ctx.package_dirdict.mount("testpackage", as_directory=True, mode="r")
ctx.package_dirdict_value = ctx.package_dirdict
ctx.package_dirdict_value.celltype = "plain"
ctx.package_dirdict_value.mount("package_dirdict.json", mode="w")
tf.package_dirdict = ctx.package_dirdict
tf.package_name = "testpackage"
tf.analyze_dependencies = mod
ctx.package = tf
ctx.package.celltype = "plain"
ctx.package.mount("package.json", mode="w")
ctx.compute()

ctx.testpackage = Module()
ctx.testpackage.code = ctx.package
def func():
    print(testpackage, dir(testpackage))
    from .testpackage import testvalue
    from .testpackage.sub.mod1 import func
    from .testpackage.sub.mod2 import func as func2
    print(testvalue)
    print(func is func2)
    print(func2())
    print(testpackage.testvalue)
    from .testpackage import mod3
    print(mod3.testvalue)
    print(mod3.testfunc(99))
    return 0

ctx.tf = func
ctx.tf.testpackage = ctx.testpackage
ctx.compute()
print(ctx.tf.exception)
print(ctx.tf.logs)

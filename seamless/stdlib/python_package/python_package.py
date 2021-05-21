from seamless.highlevel import Context, Cell, Transformer, Module
from seamless.highlevel import set_resource

# 1: Setup context

ctx = Context()

def constructor(
    ctx, libctx,
    package_dirdict, 
    package_name,
    package,
):
    mod = ctx.analyze_dependencies = Module()
    mod.code = libctx.code.analyze_dependencies.value
    tf = ctx.build_package = Transformer()
    tf.code = libctx.code.build_package.value
    ctx.package_dirdict = Cell("plain")
    tf.package_dirdict = ctx.package_dirdict
    package_dirdict.connect(ctx.package_dirdict) 
    tf.analyze_dependencies = mod
    tf.package_name = package_name
    ctx.package = tf
    ctx.package.celltype = "plain"
    package.connect_from(ctx.package)

ctx.constructor_code = Cell("code").set(constructor)
constructor_params = {
    "package_dirdict": {
        "type": "cell",
        "celltype": "plain",
        "io": "input",
        "help": """Dict containing all package code
as obtained by mounting the package directory as a plain""",
    },
    "package_name": {
        "type": "value",
        "celltype": "str",
        "default": "",
        "help": "Package name, if absolute imports are used"
    },
    "package": {
        "type": "cell",
        "celltype": "plain",
        "io": "output",
        "help": """Python package dict, to be set as the code attribute of a Module""",
    },
}
ctx.constructor_params = constructor_params
ctx.code = Context()
ctx.code.analyze_dependencies = set_resource("analyze_dependencies.py")
ctx.code.build_package= set_resource("build_package.py")

ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the contexts in a library

from seamless.highlevel.library import LibraryContainer
mylib = LibraryContainer("mylib")
mylib.python_package = ctx
mylib.python_package.constructor = ctx.constructor_code.value
mylib.python_package.params = ctx.constructor_params.value

# 4: Run test example

ctx = Context()
ctx.include(mylib.python_package)

ctx.package_dirdict = Cell("plain")
ctx.package_dirdict.mount("testpackage", as_directory=True, mode="r")
ctx.package_dirdict_value = ctx.package_dirdict
ctx.package_dirdict_value.celltype = "plain"
ctx.package_dirdict_value.mount("package_dirdict.json", mode="w")

ctx.package = Cell("plain")
ctx.package.mount("package.json", mode="w")

ctx.python_package = ctx.lib.python_package(
    package_dirdict = ctx.package_dirdict,
    package_name = "testpackage",
    package = ctx.package
)

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

if ctx.tf.status != "Status: OK":
    print(ctx.tf.status)
    print(ctx.tf.exception)
    print(ctx.tf.logs)

    import sys
    sys.exit()

# 5: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../python_package.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../python_package.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")
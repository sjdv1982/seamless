raise NotImplementedError # TODO: use highlevel.direct.module

from seamless.graphs.multi_module import mytestpackage
from seamless.workflow import Context, Cell, Module, Transformer, Resource, FolderCell

get_pypackage_dependencies_file = "get_pypackage_dependencies.py"
pypackage_to_moduledict_file = "pypackage_to_moduledict.py"

# 1: Setup

ctx = Context()
ctx.get_pypackage_dependencies_code = Resource(get_pypackage_dependencies_file)
ctx.get_pypackage_dependencies_code.celltype = "code"
ctx.get_pypackage_dependencies_code.language = "python"
ctx.pypackage_to_moduledict_code = Resource(pypackage_to_moduledict_file)
ctx.pypackage_to_moduledict_code.celltype = "code"
ctx.pypackage_to_moduledict_code.language = "python"

ctx.translate()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()


# 3: Run test example (Python)

mod = ctx.get_pypackage_dependencies = Module()
mod.code = ctx.get_pypackage_dependencies_code
tf = ctx.pypackage_to_moduledict = Transformer()
tf.code = ctx.pypackage_to_moduledict_code
ctx.pypackage_dirdict = FolderCell()
ctx.pypackage_dirdict.mount("mytestpackage", mode="r", text_only=True)
ctx.pypackage_dirdict_value = ctx.pypackage_dirdict
ctx.pypackage_dirdict_value.celltype = "plain"
ctx.pypackage_dirdict_value.mount("pypackage_dirdict.json", mode="w")
tf.pypackage_dirdict = ctx.pypackage_dirdict
tf.pins.pypackage_dirdict.celltype = "mixed"
tf.internal_package_name = "mytestpackage"
tf.get_pypackage_dependencies = mod
ctx.pypackage_moduledict = tf
ctx.pypackage_moduledict.celltype = "plain"
ctx.pypackage_moduledict.mount("pypackage_moduledict.json", mode="w")
ctx.compute()

#ctx.testpackage = Module() # will not work...
ctx.testpackage = ctx.pypackage_moduledict
def func():
    print(testpackage, dir(testpackage))
    print(testpackage.mod4, testpackage.testvalue)
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

ctx.func = func
ctx.func.testpackage = ctx.testpackage
ctx.func.testpackage.celltype = "module"
ctx.compute()

if ctx.pypackage_to_moduledict.result.value.unsilk is None:
    print("Cannot generate moduledict")
    print(ctx.pypackage_to_moduledict.exception)
    print(ctx.pypackage_to_moduledict.logs)
    import sys
    sys.exit()

if ctx.func.result.value.unsilk is None:
    print("Cannot run generated module")
    print(ctx.pypackage_to_moduledict.result.value.unsilk)
    print(ctx.func.exception)
    import sys
    sys.exit()

print(ctx.func.logs)
print(ctx.func.result.value)

# 4: Run test example (compiled transformer)
# TODO

# 5: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../multi_module.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../multi_module.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)

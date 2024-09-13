"""Instantiates a static number of copies of a given context
template: The context to instantiate
pattern: the instanced contexts are created under the name:
 ctx.pattern1, ctx.pattern2, etc., up to ncopies
ncopies: the number of copies
imports: dict of cells that are connected to each context
exports: dict of cells that each context connects to
entries: dict where the keys are keys in "imports", and values
  are paths in each context. A path can be a string or a tuple:
  the path "mycell" is instance.mycell;
  the path ("mycontext", "spam") is instance.mycontext.spam
  In the first example, connection is made from:
  - imports[key].pattern1 to pattern1.mycell
  - imports[key].pattern2 to pattern2.mycell
  - ...
exits: same as "entries", but the keys are in "exports",
  and the connection is made from value to exports[key]
  Thus, connection is made from:
    - pattern1.mycell to exports[key].pattern1
    - pattern2.mycell to exports[key].pattern2
    - ...
"""

import seamless

seamless.delegate(False)

from seamless.workflow import Context, Cell
import sys

# 1: Setup context

ctx = Context()


def constructor(
    ctx, libctx, template, pattern, ncopies, imports, exports, entries, exits
):
    def verify_path(path):
        if isinstance(path, (str, int)):
            return (path,)
        assert isinstance(path, (list, tuple)), type(path)
        for attr in path:
            assert isinstance(attr, (str, int)), path
        return path

    for k, path in list(entries.items()):
        assert k in imports, k
        entries[k] = verify_path(path)
    for k, path in list(exits.items()):
        assert k in exports, k
        exits[k] = verify_path(path)
    for n in range(ncopies):
        name = "{}{}".format(pattern, n + 1)
        instance = Context()
        instance.set_graph(template)
        setattr(ctx, name, instance)
        instance = getattr(ctx, name)  # SubContext
        for k, path in entries.items():
            import_cell = imports[k]
            subinstance = instance
            for subpathnr, subpath in enumerate(path):
                if subpath not in subinstance.get_children():
                    curr_path = path[: subpathnr + 1]
                    raise AttributeError("Invalid path {} ({})" % (path, curr_path))
                subinstance = getattr(subinstance, subpath)
            if not isinstance(subinstance, Cell):
                raise TypeError(
                    "Invalid path {} is {} instead of Cell" % (path, type(subinstance))
                )
            import_cell.connect(subinstance, source_path=name)
        for k, path in exits.items():
            export_cell = exports[k]
            subinstance = instance
            for subpathnr, subpath in enumerate(path):
                if subpath not in subinstance.get_children():
                    curr_path = path[: subpathnr + 1]
                    raise AttributeError("Invalid path {} ({})" % (path, curr_path))
                subinstance = getattr(subinstance, subpath)
            if not isinstance(subinstance, Cell):
                raise TypeError(
                    "Invalid path {} is {} instead of Cell" % (path, type(subinstance))
                )
            export_cell.connect_from(subinstance, target_path=name)


ctx.constructor_code = Cell("code").set(constructor)
ctx.constructor_params = {
    "template": "context",
    "pattern": "value",
    "ncopies": "value",
    "imports": {"type": "celldict", "io": "input"},
    "exports": {"type": "celldict", "io": "output"},
    "entries": "value",
    "exits": "value",
}
ctx.help = Cell("text")
ctx.help.mimetype = "md"
ctx.help.set(open("help/instantiate.md").read())

ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the contexts in a library

from seamless.workflow.highlevel.library import LibraryContainer

mylib = LibraryContainer("mylib")
mylib.instantiate = ctx
mylib.instantiate.constructor = ctx.constructor_code.value
mylib.instantiate.params = ctx.constructor_params.value

# 4: Run test example

ctx = Context()
ctx.include(mylib.instantiate)
ctx.a = Cell().set(
    {
        "instance1": 3,
        "instance2": 5,
        "instance3": 7,
        "instance5": 9,
    }
)
ctx.b = Cell().set(
    {
        "instance1": 8,
        "instance2": 6,
        "instance3": 4,
        "instance5": 2,
    }
)
ctx.result = Cell()
ctx.result2 = Cell()


def mul(fa, fb):
    return fa * fb


ctx.subcontext = Context()
sctx = ctx.subcontext
sctx.mul = mul
sctx.fa = Cell("int")
sctx.fb = Cell("int")
sctx.mul.fa = sctx.fa
sctx.mul.fb = sctx.fb
sctx.fmul = sctx.mul
sctx.fmul.celltype = "int"
sctx.sub = Context()
sctx.sub.fmul2 = sctx.mul
sctx.sub.fmul2.celltype = "int"

imports = {"a": ctx.a, "b": ctx.b}
exports = {"result": ctx.result, "result2": ctx.result2}
entries = {"a": "fa", "b": "fb"}
exits = {"result": "fmul", "result2": ("sub", "fmul2")}

ctx.instances = ctx.lib.instantiate(
    template=sctx,
    pattern="instance",
    ncopies=6,
    imports=imports,
    exports=exports,
    entries=entries,
    exits=exits,
)

ctx.compute()
print(ctx.result.value)
print(ctx.result2.value)
inst1 = ctx.instances.ctx.instance1
print(inst1.fa.value)
print(inst1.fb.value)
print(inst1.mul.status)

if not ctx.result.value.unsilk:
    sys.exit()

# 5: Save graph and zip

import os, json

currdir = os.path.dirname(os.path.abspath(__file__))
graph_filename = os.path.join(currdir, "../instantiate.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename = os.path.join(currdir, "../instantiate.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")

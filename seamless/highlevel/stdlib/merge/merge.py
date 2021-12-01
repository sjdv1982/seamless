from seamless.highlevel import Context, Cell
from seamless.highlevel import set_resource

# 1: Setup context

ctx = Context()

def macro_code(ctx, fallback_mode, code_start, code_update):
    reactor_params = {
        "fallback_mode": {"io": "input", "celltype": "str"},
        "upstream": {"io": "input", "celltype": "text"},
        "merged":  {"io": "output", "celltype": "text"},
        "state": {"io": "output", "celltype": "str"},
    }
    for k in "upstream_stage", "base", "modified", "conflict":
        reactor_params[k] = {
            "io": "edit",
            "celltype": "text",
            "must_be_defined": False,
        }

    merge = ctx.merge = reactor(reactor_params)
    ctx.fallback_mode = cell("str").set(fallback_mode)
    ctx.fallback_mode.connect(merge.fallback_mode)
    ctx.upstream = cell("text")
    ctx.upstream.connect(merge.upstream)
    ctx.upstream_stage = cell("text")
    ctx.upstream_stage.connect(merge.upstream_stage)
    ctx.base = cell("text")
    ctx.base.connect(merge.base)
    ctx.modified = cell("text")
    ctx.modified.connect(merge.modified)
    ctx.conflict = cell("text")
    ctx.conflict.connect(merge.conflict)
    ctx.merged = cell("text")
    merge.merged.connect(ctx.merged)
    ctx.state = cell("str")
    merge.state.connect(ctx.state)

    merge.code_start.cell().set(code_start)
    merge.code_update.cell().set(code_update)
    merge.code_stop.cell().set("")


def constructor(
    ctx, libctx,
    fallback_mode,
    upstream,
    modified, conflict,
    merged, state, base
):
    assert fallback_mode in ("upstream", "modified", "no"), fallback_mode
    m = ctx.m = Macro()
    m.code = libctx.macro_code.value
    m.fallback_mode = fallback_mode
    m.code_start = libctx.code_start.value
    m.code_update = libctx.code_update.value

    ctx.upstream = Cell("text")
    upstream.connect(ctx.upstream)
    m.pins.upstream = {"io": "input", "celltype": "text"}
    m.upstream = ctx.upstream

    ctx.modified = Cell("text")
    modified.link(ctx.modified)
    m.pins.modified = {"io": "edit", "celltype": "text"}
    m.modified = ctx.modified

    if base is not None:
        ctx.base = Cell("text")
        base.link(ctx.base)
        m.pins.base = {"io": "edit", "celltype": "text"}
        m.base = ctx.base

    ctx.conflict = Cell("text")
    conflict.link(ctx.conflict)
    m.pins.conflict = {"io": "edit", "celltype": "text"}
    m.conflict = ctx.conflict

    ctx.merged = Cell("text")
    merged.connect_from(ctx.merged)
    m.pins.merged = {"io": "output", "celltype": "text"}
    ctx.merged = m.merged

    ctx.state = Cell("text")
    state.connect_from(ctx.state)
    m.pins.state = {"io": "output", "celltype": "text"}
    ctx.state = m.state

ctx.constructor_code = Cell("code").set(constructor)
constructor_params = {
    "fallback_mode": {
        "type": "value",
        "default": "modified"
    },
    "upstream": {
        "type": "cell",
        "celltype": "text",
        "io": "input"
    },
    "base": {
        "type": "cell",
        "celltype": "text",
        "io": "edit",
        "must_be_defined": False,
    }, 
    "modified": {
        "type": "cell",
        "celltype": "text",
        "io": "edit"
    },
    "conflict": {
        "type": "cell",
        "celltype": "text",
        "io": "edit"
    },
    "merged": {
        "type": "cell",
        "celltype": "text",
        "io": "output"
    },
    "state": {
        "type": "cell",
        "celltype": "str",
        "io": "output"
    }

}

ctx.constructor_params = constructor_params
ctx.macro_code = Cell("code").set(macro_code)
ctx.code_start = set_resource("cell-merge-START.py")
ctx.code_start.celltype = "code"
ctx.code_update = set_resource("cell-merge-UPDATE.py")
ctx.code_update.celltype = "code"

ctx.compute()

# 2: obtain graph and zip

graph = ctx.get_graph()
zip = ctx.get_zip()

# 3: Package the contexts in a library

from seamless.highlevel.library import LibraryContainer
mylib = LibraryContainer("mylib")
mylib.merge = ctx
mylib.merge.constructor = ctx.constructor_code.value
mylib.merge.params = ctx.constructor_params.value

# 4: Run test example

import os
mount_dir = "/tmp/seamless-merge"
os.makedirs(mount_dir, exist_ok=True)
try:
    os.mkdir(mount_dir)
except OSError:
    pass
def mount(cell, mode="rw"):
    filename = os.path.join(mount_dir, cell._path[-1]) + ".txt"
    auth = "file" if "r" in mode else "cell"
    cell.mount(filename, mode=mode, authority=auth, persistent=True)

ctx = Context()
ctx.include(mylib.merge)

ctx.upstream = Cell("text").set("Initial version")
mount(ctx.upstream)

ctx.modified = Cell("text")
mount(ctx.modified)

ctx.conflict = Cell("text")
mount(ctx.conflict)

ctx.merged = Cell("text")
mount(ctx.merged, "w")

ctx.state = Cell("str")
mount(ctx.state, "w")

base = None
# base: disable / enable to test "base"
ctx.base = Cell("text")
mount(ctx.base)
base = ctx.base
# /base

ctx.compute()

ctx.merge = ctx.lib.merge(
    upstream=ctx.upstream,
    modified=ctx.modified,
    conflict=ctx.conflict,
    merged=ctx.merged,
    base=base,
    state=ctx.state
)

ctx.compute()
print(ctx.status)
print(ctx.merged.value)
print(ctx.state.value)
print(ctx.merge.exception)
print(ctx.merge.ctx.m.exception)
print(ctx.merge.ctx.m.ctx.base.value)

if ctx.state.value != "passthrough":
    import sys
    sys.exit()

# 5: Save graph and zip

import os, json
currdir=os.path.dirname(os.path.abspath(__file__))
graph_filename=os.path.join(currdir,"../merge.seamless")
json.dump(graph, open(graph_filename, "w"), sort_keys=True, indent=2)

zip_filename=os.path.join(currdir,"../merge.zip")
with open(zip_filename, "bw") as f:
    f.write(zip)
print("Graph saved")
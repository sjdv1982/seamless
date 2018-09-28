from seamless.highlevel import Context, Reactor, Cell, Link, stdlib
from seamless.lib import set_resource

ctx = Context()
merge = ctx.merge = Reactor()
merge._get_hrc()["plain"] = True ### TODO: direct API from highlevel.Reactor

merge.set_pin("fallback", io="input")

merge.set_pin("upstream", io="input", access_mode="text")
merge.set_pin("upstream_stage", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("base", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("modified", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("conflict", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("merged", io="output", access_mode="text")

merge.set_pin("mode", io="output")

merge.fallback = "no"
#TODO: add the validator to the schema of the .fallback property
#  (requires that .add_validator and ._set_property/._set_method become schema methods)
def validate_fallback(self):
    assert self.fallback in ("upstream", "modified", "no"), self.fallback
merge.io.handle.add_validator(validate_fallback)

merge.code_start = set_resource("cell-merge-START.py")
merge.code_update = set_resource("cell-merge-UPDATE.py")
merge.code_stop = ""

# Public cells
ctx.upstream = Cell()
ctx.upstream.celltype = "text"
merge.upstream = ctx.upstream

ctx.modified = Cell()
ctx.modified.celltype = "text"
ctx.link_modified = Link(ctx.modified, merge.modified)

ctx.conflict = Cell()
ctx.conflict.celltype = "text"
ctx.link_conflict = Link(ctx.conflict, merge.conflict)

ctx.fallback = merge.fallback.value
ctx.fallback.celltype = "text"
merge.fallback = ctx.fallback

ctx.merged = merge.merged
ctx.merged.celltype = "text"

if __name__ == "__main__":

    #Mounting of graph and cells
    import os, tempfile
    mount_dir = os.path.join(tempfile.gettempdir(), "seamless-merge")
    ctx.mount_graph(mount_dir, persistent=True)
    try:
        os.mkdir(mount_dir)
    except OSError:
        pass
    def mount(cell, mode="rw"):
        filename = os.path.join(mount_dir, cell._path[-1]) + ".txt"
        auth = "file" if "r" in mode else "cell"
        cell.mount(filename, mode=mode, authority=auth, persistent=True)

    # Setting up interactive unit test
    ctx.upstream = "Initial version"
    mount(ctx.upstream)

    ctx.upstream_stage = merge.upstream_stage
    ctx.upstream_stage.celltype = "text"
    mount(ctx.upstream_stage, "w")

    ctx.base = Cell()
    ctx.base.celltype = "text"
    ctx.base = merge.base
    mount(ctx.base, "w")

    mount(ctx.modified)
    mount(ctx.conflict)
    mount(ctx.merged, "w")

    ctx.mode = merge.mode
    ctx.mode.celltype = "text"
    mount(ctx.mode, "w")

    ctx.equilibrate()
else:
    stdlib.merge = ctx

ctx.equilibrate()

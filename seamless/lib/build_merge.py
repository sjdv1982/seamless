from seamless.highlevel import Context, Reactor, Cell, Link, stdlib
from seamless.lib import set_resource

ctx = Context()
merge = ctx.merge = Reactor()
merge._get_hrc()["plain"] = True
#TODO: schema for fallback: must be in "upstream", "modified", "no"
merge.set_pin("upstream", io="input", access_mode="text")
merge.set_pin("fallback", io="input", access_mode="text")
merge.set_pin("upstream_stage", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("base", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("modified", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("conflict", io="edit", access_mode="text", must_be_defined=False)
merge.set_pin("merged", io="output", access_mode="text")
merge.code_start = set_resource("cell-merge-start.py")
merge.code_update = set_resource("cell-merge-update.py")
merge.code_stop = ""

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
    merge.fallback = "no"

    ctx.inp = "Initial version"
    ctx.inp.celltype = "text"
    merge.upstream = ctx.inp
    mount(ctx.inp)

    ctx.upstream_stage = Cell()
    ctx.upstream_stage.celltype = "text"
    ctx.upstream_stage = merge.upstream_stage
    mount(ctx.upstream_stage, "w")

    ctx.base = Cell()
    ctx.base.celltype = "text"
    ctx.base = merge.base
    mount(ctx.base, "w")

    ctx.modified = Cell()
    ctx.modified.celltype = "text"
    ctx.link_modified = Link(ctx.modified, merge.modified)
    mount(ctx.modified)

    ctx.conflict = Cell()
    ctx.conflict.celltype = "text"
    ctx.link_modified = Link(ctx.conflict, merge.conflict)
    mount(ctx.conflict)

    ctx.equilibrate()
    print("Reactor status:", ctx.merge.self.status())
    print("START")
else:
    stdlib.browser = ctx

ctx.equilibrate()

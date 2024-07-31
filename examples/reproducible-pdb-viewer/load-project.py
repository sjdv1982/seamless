
PROJNAME = "reproducible-pdb-viewer"

DELEGATION_LEVEL = 0

"""
Change DELEGATION_LEVEL to the appropriate level:

DELEGATION_LEVEL = 0
Runs load_vault on project startup
Runs save_vault on project save.
All input/output buffers and results are held in memory.

DELEGATION_LEVEL = 1
External read buffer servers/folders may be configured. 
On project startup, run load_vault if vault/ exists.
On project save, run save_vault if vault/ exists

DELEGATION_LEVEL = 2
Buffers are stored in an external buffer server. 
Such a server can be launched using "seamless-delegate none"
Vaults are being ignored on project load/save. You are recommended to upload the vault/ directory 
using "seamless-upload"

DELEGATION_LEVEL = 3
Buffers are stored in an external buffer server.
Results are stored as checksums in a database server.
Such servers can be launched using "seamless-delegate none"
Vaults are being ignored on project load/save. You are recommended to upload the vault/ directory 
using "seamless-upload"

DELEGATION_LEVEL = 4
All jobs, buffers and results are delegated to an external assistant
Such an assistant can be launched using "seamless-delegate <name of assistant>" 
Vaults are being ignored on project load/save. You are recommended to upload the vault/ directory 
using "seamless-upload"
"""

import os, sys, shutil
import seamless, seamless.config
from seamless import (Context, Cell, Transformer, Module, Macro, 
                                SimpleDeepCell, FolderCell, DeepCell, DeepFolderCell)

def pr(*args):
    print(*args, file=sys.stderr)

_curr_delegation_level = seamless.config.get_delegation_level()
if _curr_delegation_level is None:
    seamless.delegate(DELEGATION_LEVEL)
elif int(_curr_delegation_level) != DELEGATION_LEVEL:
    pr("DELEGATION_LEVEL overridden to {} by previous seamless.delegate() call".format(_curr_delegation_level))
    DELEGATION_LEVEL = int(_curr_delegation_level)


ctx = None
webctx = None
save = None
export = None

async def define_graph(ctx):
    """Code to define the graph
    Leave this function empty if you want load() to load the graph from graph/PROJNAME.seamless 
    """
    pass

def load_ipython():
    import asyncio
    import seamless
    loop = seamless._original_event_loop
    asyncio.set_event_loop(loop)
    coro = load()
    loop.run_until_complete(coro)

async def load():
    from seamless.metalevel.bind_status_graph import bind_status_graph_async
    import json

    global ctx, webctx, save, export

    try:
        ctx
    except NameError:
        pass
    else:
        if ctx is not None:
            pr('"ctx" already exists. To reload, do "ctx = None" or "del ctx" before "await load()"')
            return

    for f in (
        "web/index-CONFLICT.html",
        "web/index-CONFLICT.js",
        "web/webform-CONFLICT.txt",
    ):
        if os.path.exists(f):
            try:
                if open(f).read().rstrip("\n ") in ("", "No conflict"):
                    continue
            except UnicodeDecodeError:
                continue
            dest = f + "-BAK"
            if os.path.exists(dest):
                os.remove(dest)            
            pr("Existing '{}' found, moving to '{}'".format(f, dest))
            shutil.move(f, dest)
    ctx = Context()
    empty_graph = ctx.get_graph()
    try:
        seamless._defining_graph = True
        await define_graph(ctx)
    finally:
        try:
            del seamless._defining_graph
        except AttributeError:
            pass
    new_graph = ctx.get_graph()
    graph_file = "graph/" + PROJNAME + ".seamless"
    if DELEGATION_LEVEL == 0: 
        ctx.load_vault("vault")
    elif DELEGATION_LEVEL == 1:
        if os.path.exists("vault"):
            ctx.load_vault("vault")
    if new_graph != empty_graph:
        pr("*** define_graph() function detected. Not loading '{}'***\n".format(graph_file))
    else:
        pr("*** define_graph() function is empty. Loading '{}' ***\n".format(graph_file))
        graph = json.load(open(graph_file))        
        ctx.set_graph(graph, mounts=True, shares=True)
        await ctx.translation(force=True)

    status_graph = json.load(open("graph/" + PROJNAME + "-webctx.seamless"))

    webctx = await bind_status_graph_async(
        ctx, status_graph,
        mounts=True,
        shares=True
    )
    
    def save():
        import os, itertools, shutil

        def backup(filename):
            if not os.path.exists(filename):
                return filename
            for n in itertools.count():
                n2 = n if n else ""
                new_filename = "{}.bak{}".format(filename, n2)
                if not os.path.exists(new_filename):
                    break
            shutil.move(filename, new_filename)
            return filename

        try:
            ctx.translate()
        except Exception:
            pass
        ctx.save_graph(backup("graph/" + PROJNAME + ".seamless"))
        try:
            webctx.translate()
        except Exception:
            pass        
        webctx.save_graph(backup("graph/" + PROJNAME + "-webctx.seamless"))
        if DELEGATION_LEVEL == 0: 
            ctx.save_vault("vault")
            webctx.save_vault("vault")
        elif DELEGATION_LEVEL == 1:
            if os.path.exists("vault"):
                ctx.save_vault("vault")
                webctx.save_vault("vault")

    def export():
        filename = "graph/reproducible-pdb-viewer.zip"
        ctx.save_zip(filename)
        pr(f"{filename} saved")
        filename = "graph/reproducible-pdb-viewer-webctx.zip"
        webctx.save_zip(filename)
        pr(f"{filename} saved")

    await ctx.translation(force=True)
    await ctx.translation(force=True)
    
    pr("""Project loaded.

    Main context is "ctx"
    Web/status context is "webctx"

    Open http://localhost:<REST server port> to see the web page
    Open http://localhost:<REST server port>/status/status.html to see the status

    Run save() to save the project workflow file.
    Run export() to generate zip files for web deployment.
    """)

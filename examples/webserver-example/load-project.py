
PROJNAME = "webserver-example"

import os, sys, shutil

import seamless

from seamless.highlevel import Context, Cell, Transformer, Module, Macro

ctx = None
webctx = None
save = None

def pr(*args):
    print(*args, file=sys.stderr)

async def define_graph(ctx):
    """Code to define the graph
    Leave this function empty if you want load() to load the graph from graph/PROJNAME.seamless 
    """
    pass

def load_database():
    # To connect to a Seamless database, specify the following environment variables:
    # SEAMLESS_DATABASE_IP, SEAMLESS_DATABASE_PORT
    #
    # They are passed into the Seamless Docker container when you run 
    #  seamless-load-project, seamless-jupyter, etc.
    # Seamless provides default values for these environment variables
    # These defaults will connect to the database started with seamless-database command.
    # 
    # Then, uncomment the following lines:
    # To read buffers and transformation results from the database:
    #
    # seamless.database_cache.connect()  
    #
    # To write buffers and transformation results into the database:
    #
    # seamless.database_sink.connect()
    return

COMMUNION_MSG=""
async def load_communion():
    global COMMUNION_MSG
    # To connect to a Seamless communion peer, such as jobless or a jobslave,
    # specify the following environment variables:
    # SEAMLESS_COMMUNION_IP
    # SEAMLESS_COMMUNION_PORT
    # or: SEAMLESS_COMMUNION_INCOMING (comma-separated list of multiple peers, as IP:port,IP:port,...)
    #
    # These are passed into the Seamless Docker container when you run 
    #  seamless-load-project, seamless-jupyter, etc.
    # Seamless provides default values for these environment variables
    # These defaults will try to connect to jobless.
    # 
    # Then, uncomment the following lines:
    #
    # await seamless.communion_server.start_async()
    # npeers = len(seamless.communion_server.peers)
    # COMMUNION_MSG="\n\n{} communion peer(s) found.".format(npeers)
    return

async def load():
    from seamless.metalevel.bind_status_graph import bind_status_graph_async
    import json

    global ctx, webctx, save

    try:
        ctx
    except NameError:
        pass
    else:
        if ctx is not None:
            pr('"ctx" already exists. To reload, do "ctx = None" or "del ctx" before load()')
            return
    load_database()    
    await load_communion()

    for f in (
        "web/index-CONFLICT.html",
        "web/index-CONFLICT.js",
        "web/webform-CONFLICT.txt",
    ):
        if os.path.exists(f):
            if open(f).read().rstrip("\n ") in ("", "No conflict"):
                continue
            dest = f + "-BAK"
            if os.path.exists(dest):
                os.remove(dest)            
            pr("Existing '{}' found, moving to '{}'".format(f, dest))
            shutil.move(f, dest)
    ctx = Context()
    empty_graph = await ctx._get_graph_async(copy=True)
    try:
        seamless._defining_graph = True
        await define_graph(ctx)
    finally:
        try:
            del seamless._defining_graph
        except AttributeError:
            pass
    new_graph = await ctx._get_graph_async(copy=True)
    graph_file = "graph/" + PROJNAME + ".seamless"
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

        ctx.save_graph(backup("graph/" + PROJNAME + ".seamless"))
        webctx.save_graph(backup("graph/" + PROJNAME + "-webctx.seamless"))
        ctx.save_vault("vault")
        webctx.save_vault("vault")

    pr("""Project loaded.

    Main context is "ctx"
    Web/status context is "webctx"

    Open http://localhost:<REST server port> to see the web page
    Open http://localhost:<REST server port>/status/status.html to see the status

    Run save() to save the project{}
    """.format(COMMUNION_MSG))

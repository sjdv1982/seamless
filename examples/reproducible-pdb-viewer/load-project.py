"""
TODO: 
- Finalize web form params (ngl viewer dimension)
- Deepcell keys: rip get_keys, use ctx.pdb.keyorder to set cell
- Port to Jupyter notebook
"""
PROJNAME = "reproducible-pdb-viewer"

import os, sys, shutil

import seamless

from seamless.highlevel import Context, Cell, Transformer, Module, Macro, DeepCell, SimpleDeepCell
from seamless.highlevel import stdlib
from seamless.highlevel import webunits

ctx = None
webctx = None
save = None

def pr(*args):
    print(*args, file=sys.stderr)

async def define_graph(ctx):
    """Code to define the graph
    Leave this function empty if you want load() to load the graph from graph/PROJNAME.seamless 
    """
    ctx.pdb = DeepCell()
    
    # Weakly reproducible way (relies on FAIR server to get the checksum)
    date = "2022-11-27"
    distribution = DeepCell.find_distribution("pdb", date=date, format="mmcif")
    ctx.pdb.define(distribution)
    print()
    print("*" * 50)
    print("PDB date:", date)
    print("Number of index keys (PDB entries): ", ctx.pdb.nkeys )
    pdb_index_size = "{:d} MiB".format(int(ctx.pdb.index_size/10**6))
    print("Size of the checksum index: ", pdb_index_size )
    if ctx.pdb.content_size is None:
        pdb_size = "<Unknown>"
    else:
        pdb_size = "{:d} GiB".format(int(ctx.pdb.content_size/10**9))
    print("Total size of the Protein Data Bank (mmCIF format):", pdb_size )
    print("*" * 50)
    print()
    print("Download index file")
    await ctx.computation()
    print("Access PDB entry 1avx")
    pdb_data = ctx.pdb.access("1avx")
    print(pdb_data[:1000])

    # TODO: make a stdlib for this
    ctx.pdb2 = Cell("checksum")
    ctx.pdb2 = ctx.pdb
    ctx.pdb3 = Cell("plain")
    ctx.pdb3 = ctx.pdb2
    def get_codes(pdb):
        return list(pdb.keys())
    ctx.get_codes = get_codes
    ctx.get_codes.pdb = ctx.pdb3
    ctx.pdb_codes = ctx.get_codes.result
    ctx.pdb_codes.celltype = "plain"

    ctx.pdb_code = Cell("str").set("1avx")
    webunits.bigselect(ctx, options=ctx.pdb_codes, selected=ctx.pdb_code)

    ctx.include(stdlib.select)
    ctx.pdb_structure = Cell("text")
    ctx.select_pdb = ctx.lib.select(
        celltype="text",
        input=ctx.pdb,
        selected=ctx.pdb_code,
        output=ctx.pdb_structure,
    )
    ctx.representation = Cell("yaml").share(readonly=False)
    ctx.representation.mount("representation.yaml")
    ctx.representation2 = Cell("plain")
    ctx.representation2 = ctx.representation
    webunits.nglviewer(ctx, ctx.pdb_structure, ctx.representation2, format="cif")
    await ctx.translation()

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
    # If these environment variables are not defined, 
    # Seamless provides default values for them.
    # These default values will try to connect to jobless.
    # 
    # Then, uncomment the following lines:
    #
    # seamless.communion_server.configure_master({
    #     "buffer": True,
    #     "buffer_status": True,
    #     "buffer_info": True,
    #     "transformation_job": True,
    #     "transformation_status": True,
    #     "semantic_to_syntactic": True,
    # })
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

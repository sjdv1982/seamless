
PROJNAME = "share-pdb-webunit"

import os, sys, shutil
from copy import deepcopy
import json

import seamless

from seamless.highlevel import Context, Cell, Transformer, Module, Macro

ctx = None
webctx = None
save = None


def make_share_pdb_webunit_dict():
    result = {
        "@name": "nglviewer"
    }
    result["structures"] = {
        "type": "cell",
        "share": "structures.json",
        "readonly": True,
    }
    result["representation"] = {
        "type": "cell",
        "share": "representation.json",
        "readonly": True,
        "default": {
            "DEFAULT": {
                "type": "cartoon",
                "params": {},
            }
        }
    }
    result["format"] = {
        "type": "value"
    }
    return result

share_pdb_webunit_dict = make_share_pdb_webunit_dict()

def add_webunit(ctx, webunit_dict, params):
    from seamless.highlevel import Cell
    from seamless.highlevel.Base import Base
    assert "@name" in webunit_dict
    name = webunit_dict["@name"]

    webunits = ctx._graph.params.get("webunits")
    if webunits is None:
        webunits = {}
    sibling_webunits = webunits.get(name)
    if sibling_webunits is None:
        sibling_webunits = []
    sib_id = len(sibling_webunits) + 1

    id_ = "{}_{:d}".format(name, sib_id)
    new_webunit = {
        "id": id_
    }
    parameters = {}
    cells = {}
    new_webunit["parameters"] = parameters
    new_webunit["cells"] = cells

    for param in webunit_dict:
        if param.startswith("@"):
            continue
        if param not in params:
            raise TypeError("Missing parameter '{}'".format(param))
        conf = webunit_dict[param]
        type_ = conf.get("type")
        if type_ == "cell":
            try:
                webunit_dict[param]["share"]
            except KeyError:
                raise KeyError((param, "share")) from None
            cell = params[param]
            if not isinstance(cell, Cell):
                raise TypeError((param, type(cell)))
            cell.value
            value = cell.value

        elif type_ == "value":
            value = params[param]
            if isinstance(value, Base):
                raise TypeError((param, type(value)))
            try:
                json.dumps(value)
            except Exception:
                raise TypeError((param,"Not JSON-serializable")) from None
            parameters[param] = deepcopy(value)
        else:
            raise TypeError(param, type_)

    for param in webunit_dict:        
        if param.startswith("@"):
            continue
        conf = webunit_dict[param]
        type_ = conf.get("type")        
        if type_ == "cell":
            cell = params[param]
            value = cell.value
            if value is None:
                default = webunit_dict[param].get("default")
                if default is not None:
                    cell.set(default)
            share = cell._get_hcell().get("share")
            if share is None:
                readonly = webunit_dict[param].get("readonly", True)
                sharepath = id_ + "/" + webunit_dict[param]["share"]
                cell.share(sharepath, readonly=readonly)
            else:
                sharepath = share["path"]
            cells[param] = "/".join(cell._path)
        
    sibling_webunits.append(new_webunit)
    webunits[name] = sibling_webunits
    ctx._graph.params["webunits"] = webunits

def add_share_pdb_webunit(ctx, structures_cell, representation_cell, format):
    params = {
        "structures": structures_cell,
        "representation": representation_cell,
        "format": format
    }
    add_webunit(ctx, share_pdb_webunit_dict, params)

def pr(*args):
    print(*args, file=sys.stderr)

async def define_graph(ctx):
    """Code to define the graph
    Leave this function empty if you want load() to load the graph from graph/PROJNAME.seamless 
    """
    ctx.pdb = Cell("text").set(open("1b7f.pdb").read())
    ctx.structures = Cell()
    ctx.structures["1b7f"] = ctx.pdb
    ctx.structures.datatype = "plain"
    ctx.structures.share("struc")
    ctx.representation = Cell("plain") 
    ctx.representation.mount("representation.json")
    ctx.blah = Cell("plain")
    ctx.blah.share("BLAH")
    ctx.sub = Context()
    ctx.sub.mycell = Cell("int").set(42)
    ctx.sub.mycell.share()
    await ctx.computation()

    add_share_pdb_webunit(ctx, ctx.structures, ctx.representation, "pdb")
    print(ctx.get_graph()["params"])
    await ctx.computation()

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
    webctx.seamless_client_js.mount("seamless-client.js")
    await webctx.computation()

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

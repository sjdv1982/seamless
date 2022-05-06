import sys, os, shutil, json
from seamless.highlevel import Context
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument(
    "project_name",
    help="Name of the project",
)
args = parser.parse_args()
project_name = args.project_name

def pr(*args):
    print(*args, file=sys.stderr)

notebook = r"""{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": 1,
   "metadata": {
    "collapsed": true
   },
   "outputs": [],
   "source": [
    "%run -i load-project.py\n",
    "await load()"
   ]
  }
 ],
 "metadata": {},
 "nbformat": 4,
 "nbformat_minor": 2
}"""

subpaths = [
    "web",
    "graph",
    "vault"
]
for subpath in subpaths:
    if os.path.exists(subpath):
        pr("%s/ already exists, aborting..." % subpath)
        exit(1)

for subpath in subpaths:
    os.mkdir(subpath)

import seamless
seamless_dir = os.path.dirname(seamless.__file__)

empty = Context()
empty.save_graph("graph/{0}.seamless".format(project_name))
del empty

f = "webgen.seamless"
source = os.path.join(seamless_dir, "graphs", f)
dest = os.path.join("graph", "{0}-webctx.seamless".format(project_name))
shutil.copy(source, dest)
graph = json.load(open(dest))

ctx = Context()
ctx.add_zip(os.path.join(seamless_dir, "graphs", "webgen.zip"))
ctx.set_graph(graph)
ctx.save_vault("vault")

gitignore = """# Seamless vault files and backups

# 1. Independent, big buffers. Uncomment the following line to remove them from version control
### vault/independent/big/*

# 2. Dependent, big buffers. Comment out the following line to put them under version control
vault/dependent/big/*

# 3. Dependent, small buffers. Comment out the following line to put them under version control
vault/dependent/small/*

# 4. Backups of the Seamless graph. Comment out the following line to put them under version control
graph/*.seamless.bak*

# In all cases, at least keep an empty directory for the vaults
!vault/*/*/.gitkeep

"""

if os.path.exists(".gitignore"):
    pr(".gitignore file already exists. Adding Seamless entries...")
    with open(".gitignore", "a") as f:
        f.write("\n" + gitignore)
else:
    with open(".gitignore", "w") as f:
        f.write(gitignore)

code = '''
PROJNAME = "%s"

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
    # COMMUNION_MSG="\\n\\n{} communion peer(s) found.".format(npeers)
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
            if open(f).read().rstrip("\\n ") in ("", "No conflict"):
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
        pr("*** define_graph() function detected. Not loading '{}'***\\n".format(graph_file))
    else:
        pr("*** define_graph() function is empty. Loading '{}' ***\\n".format(graph_file))
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
''' % (project_name,)

with open("load-project.py", "w") as f:
    f.write(code)

with open("{0}.ipynb".format(project_name), "w") as f:
    f.write(notebook)

pr("""Project {0} created.

- Use seamless-load-project to start up IPython
or:
- Use seamless-jupyter to start up Jupyter
  and in the Jupyter browser window,
  open /home/jovyan/cwd/{0}.ipynb

If Seamless needs to execute Docker transformers:
- Use seamless-load-project-trusted to start up IPython
or:
- Use seamless-jupyter-trusted to start up Jupyter
  and in the Jupyter browser window,
  open /home/jovyan/cwd/{0}.ipynb
""".format(project_name))
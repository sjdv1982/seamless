import sys, os, shutil, json
from seamless.highlevel import Context

project_name = sys.argv[1]

def pr(*args):
    print(*args, file=sys.stderr)

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
empty.save_graph("graph/%s.seamless" % project_name)
del empty

f = "webgen.seamless"
source = os.path.join(seamless_dir, "graphs", f)
dest = os.path.join("graph", "testproject-webctx.seamless")
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

from seamless.highlevel import Context, Cell, Transformer

ctx = None
webctx = None
save = None

async def load():
    from seamless.metalevel.bind_status_graph import bind_status_graph_async
    import json

    global ctx, webctx, save
    graph = json.load(open("graph/" + PROJNAME + ".seamless"))
    ctx = Context()
    ctx.load_vault("vault")
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
        webctx.save_graph(backup("graph/" + PROJNAME + "-monitoring.seamless"))
        ctx.save_vault("vault")
        webctx.save_vault("vault")

    print("""Project loaded.

    Main context is "ctx"
    Web/status context is "webctx"
    Open http://localhost:<REST server port> to see the web page
    Open http://localhost:<REST server port>/status/status.html to see the status
    Run save() to save the project
    """)
''' % (project_name,)

with open("load-project.py", "w") as f:
    f.write(code)

pr("Project created. Use seamless-load-project to start up IPython")
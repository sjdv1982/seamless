import glob, os, json
from ..highlevel.library import LibraryContainer
from ..highlevel.library.library import set_library
from ..midlevel.StaticContext import StaticContext
lib = LibraryContainer("stdlib")

currdir=os.path.dirname(os.path.abspath(__file__))
graph_files = glob.glob("{}/*.seamless".format(currdir))
for graph_file in graph_files:
    graph_name0 = os.path.split(graph_file)[1]
    graph_name = os.path.splitext(graph_name0)[0]
    with open(graph_file) as f:
        graph = json.load(f)
    zipfile = os.path.join(currdir, graph_name) + ".zip"
    with open(zipfile, "rb") as f:
        zip = f.read()
    sctx = StaticContext.from_graph(graph)
    sctx.add_zip(zip)
    if graph_name.startswith("lib-"):
        for child in sctx.get_children():
            ssctx = getattr(sctx, child)
            if not isinstance(ssctx, StaticContext):
                continue
            constructor = ssctx.constructor_code.value
            constructor_params = ssctx.constructor_params.value
            path = ("stdlib", graph_name[len("lib-"):], child)
            sub_graph = ssctx.static.get_graph()
            set_library(path, sub_graph, zip, constructor, constructor_params)
    else:
        constructor = sctx.constructor_code.value
        constructor_params = sctx.constructor_params.value
        path = ("stdlib", graph_name)
        set_library(path, graph, zip, constructor, constructor_params)
    globals()[path[1]] = getattr(lib, path[1])
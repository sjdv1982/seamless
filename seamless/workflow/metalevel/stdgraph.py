"""Access to Seamless standard graphs, stored in /seamless/graphs/.
The main function of the standard graphs is to aid in translation,
in particular:
    - multi-file modules
    - compiled transformers
    - bash transformers without Docker
    - bash transformers with Docker
(there other graphs in that directory, related to visualization, 
but these are simply copied once into a new project)

This file contains facilities to load standard graphs, 
and to manipulate them (and hence influence translation) dynamically.
"""

from io import BytesIO
from zipfile import ZipFile
import seamless, os, json
from ..midlevel.StaticContext import StaticContext

seamless_dir = os.path.dirname(seamless.__file__)
stdgraph_dir = os.path.join(seamless_dir, "workflow", "graphs")

_cache = {}


def _load(graphname):
    graphfile = os.path.join(stdgraph_dir, graphname + ".seamless")
    zipfile = os.path.join(stdgraph_dir, graphname + ".zip")
    with open(zipfile, "rb") as f:
        zipdata = f.read()
    graph = json.load(open(graphfile))
    _cache[graphname] = graph, zipdata


def load(graphname):
    """Loads graph from Seamless standard graph directory
    (/seamless/workflow/graphs/). A StaticContext is returned.
    StaticContexts are cached."""
    if graphname not in _cache:
        _load(graphname)
    graph, zipdata = _cache[graphname]
    sctx = StaticContext.from_graph(graph)
    sctx.add_zip(zipdata)
    return sctx


def get(graphname):
    """Returns graph and zip data (as ZipFile) associated with graphname.
    Loads those data from file, if needed"""
    if graphname not in _cache:
        _load(graphname)
    graph, zipdata = _cache[graphname]
    archive = BytesIO(zipdata)
    zipfile = ZipFile(archive, "r")
    return graph, zipfile


def set(graphname, graph, zip):
    """Sets graph and zip data associated with graphname.
    They will cached, i.e. they will be returned by
    subsequent load() and get() calls.
    However, they are not written to any file on disk"""
    if isinstance(zip, bytes):
        zipdata = zip
    elif isinstance(zip, ZipFile):
        zipdata = zip.read()
    elif hasattr(zip, "read") and callable(zip.read):
        zipdata = zip.read()
    _cache[graphname] = graph, zipdata

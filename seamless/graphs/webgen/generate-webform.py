# For the docstring, do `webctx.generate_webform?` in IPython

# input: graph

from copy import deepcopy

webdefaults = {
    "int": 0,
    "float": 0.0,
    "str": "",
    "plain": {},
    "text": "",
    "bool": False,
    "bytes": None,
}

cells = {}
extra_cells = {}
extra_components = []
transformers = {}
webform = {
    "index": {
        "title": "Seamless webform",
    },
    "cells": cells,
    "extra_components": extra_components,
    "transformers": transformers,
}
default_transformer = {
    "component": "transformer-status",
    "params": {}
}
for node in graph["nodes"]:
    if "UNTRANSLATED" in node:
        continue
    if "UNSHARE" in node:
        continue
    path0 = "." + ".".join(node["path"])
    key = "/".join(node["path"])
    if node["type"] == "transformer":
        tf = deepcopy(default_transformer)
        tf["params"].update({"title": "Transformer " + node["path"][-1]})
        transformers[key] = tf
        continue
    if node["type"] != "cell":
        continue
    if "share" not in node:
        continue
    path = node["share"].get("path")
    celltype = node["celltype"]
    if celltype == "structured":
        celltype = node["datatype"]
    share = {"read": True}
    cell = {
        "celltype": celltype,
    }
    cellname = node["path"][-1]
    if cellname.find(".") > -1:
        share["auto_read"] = False
    else:
        share["auto_read"] = True
    if not node["share"].get("readonly", True):
        share["write"] = True

    if path is not None and path != key:
        if celltype in ("plain", "float", "int", "bool", "str"):
            share["encoding"] = "json"
        elif celltype == "text":
            share["encoding"] = "text"
        elif celltype == "bytes":
            pass
        else:
            continue
        cell["share"] = share
        cell["path"] = path
        cell["webdefault"] = webdefaults[cell["celltype"]]
        extra_cells[key] = cell

        continue

    params = {}
    if celltype in ("float", "int"):
        params["title"] = "Cell " + cellname.capitalize()
        if not node["share"].get("readonly", True):
            cell["component"] = "slider"
            params["min"] = 0
            params["max"] = 100
        else:
            cell["component"] = "numberinput"
            params["editable"] = False
        share["encoding"] = "json"  # also for "str", "plain", "bool"
    elif celltype in ("text", "cson", "yaml"):
        params["title"] = "Cell " + cellname.capitalize()
        if not node["share"].get("readonly", True):
            cell["component"] = "input"
            params["type"] = "textarea"
            params["maxlength"] = 1000
        else:
            cell["component"] = "card"
        share["encoding"] = "text"
    elif celltype == "str":
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "input"
        params["type"] = "input"
        params["maxlength"] = 100
        if node["share"].get("readonly", True):
            params["editable"] = False
        else:
            params["editable"] = True
        share["encoding"] = "json"
    elif celltype == "plain":
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "card"
        share["encoding"] = "json"
    elif celltype == "bytes":
        params["title"] = "Cell " + cellname.capitalize()        
        if node["share"].get("readonly", True):
            cell["component"] = ""
        else:
            cell["component"] = "fileupload"
        share["encoding"] = "text"
    elif celltype == "bool":
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "checkbox"
        if node["share"].get("readonly", True):
            params["editable"] = False
        else:
            params["editable"] = True
        share["encoding"] = "json"
    else:
        if node["celltype"] == "structured" and node["datatype"] == "mixed":
            raise TypeError("""Need a datatype for structured cell {} .
The web interface generator only supports structured cells if their
datatype attribute is set to a supported celltype.
Supported celltypes: text, int, float, bool, str, plain, or bytes.""".format(path0))
        else:
            raise TypeError("""Unsupported celltype "{}" for cell {} .
Supported celltypes: text, int, float, bool, str, plain, or bytes.""".format(celltype, path0))
    cell.update({
        "params": params,
        "share": share,
    })
    cell["webdefault"] = webdefaults[cell["celltype"]]
    cells[key] = cell
    if not len(extra_components):
        extra_components.append(
            {
                "id": "EXAMPLE_ID",
                "cell": key,
                "component": "",
                "params": {},
            }
        )
webcells = {}
for webunit_name, webunits in graph["params"].get("webunits", {}).items():
    for webunit in webunits:
        extra_components.append(
            {
                "id": webunit["id"],
                "cells": webunit["cells"],
                "component": webunit_name,
                "params": webunit["parameters"],
            }
        )
        webcells.update(webunit.get("webcells", {}))

if len(extra_cells):
    webform["extra_cells"] = extra_cells
    
if len(webcells):
    webform["webcells"] = webcells

result = webform

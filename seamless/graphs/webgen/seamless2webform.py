"""Generates a webform dict from
The webform dict is used by generate-webpage.py to create an index.html + index.js

It creates a default entry in the webform for each shared celltype
You can modify this script to change the defaults

auto_read: the web page will download the value of the cell whenever it changes
"""
# input: graph

from copy import deepcopy

cells = {}
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
    if path is not None and len(path.split(".")[1:]) and path.split(".")[-1] in ("js", "html"):
        continue
    celltype = node["celltype"]
    if celltype == "structured":
        celltype = node["datatype"]
    params = {}
    share = {}
    cell = {
        "celltype": celltype,
    }
    cellname = node["path"][-1]
    if cellname.find(".") > -1:
        params["auto_read"] = False
    else:
        params["auto_read"] = True
    if celltype in ("float", "int"):
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()
        if not node["share"].get("readonly", True):
            cell["component"] = "slider"
            params["min"] = 0
            params["max"] = 100
            share["write"] = True
        else:
            cell["component"] = "numberinput"
            params["editable"] = False
        share["encoding"] = "json"  # also for "str", "plain", "bool"
    elif celltype == "text":
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()
        if not node["share"].get("readonly", True):
            cell["component"] = "fileupload"
            share["write"] = True
        else:
            cell["component"] = "card"
        share["encoding"] = "text"
    elif celltype == "str":
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "input"
        if node["share"].get("readonly", True):
            params["editable"] = False
        else:
            share["write"] = True
            params["editable"] = True
        share["encoding"] = "json"
    elif celltype == "plain":
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "card"
        share["encoding"] = "json"
    elif celltype == "bytes":
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()        
        if node["share"].get("readonly", True):
            cell["component"] = ""
        else:
            cell["component"] = "fileupload"
            share["write"] = True
        share["encoding"] = "text"
    else:
        raise NotImplementedError(celltype)
    cell.update({
        "params": params,
        "share": share,
    })
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

result = webform

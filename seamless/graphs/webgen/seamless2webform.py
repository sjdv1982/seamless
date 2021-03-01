# input: graph

cells = {}
webform = {
    "index": {
        "title": "Seamless webform",
    },
    "cells": cells,
}
for node in graph["nodes"]:
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
            raise NotImplementedError("writeable text cell")
        else:
            cell["component"] = "card"
        share["encoding"] = "text"
    elif celltype == "plain":
        share["read"] = True
        params["title"] = "Cell " + cellname.capitalize()
        cell["component"] = "card"
        share["encoding"] = "json"
    else:
        raise NotImplementedError(celltype)
    cell.update({
        "params": params,
        "share": share,
    })
    cellkey = "_".join(node["path"])
    cells[cellkey] = cell

result = webform
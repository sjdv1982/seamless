import makefun
import functools
import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")
import os
import glob
import json
import sys
from copy import deepcopy
import traceback
from inspect import Signature, Parameter
from typing import *


def _add_webunit_instance(ctx, webunit_dict, **params):
    from seamless.workflow import Cell
    from seamless import Base

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
    new_webunit = {"id": id_}
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
                raise TypeError((param, "Not JSON-serializable")) from None
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
            allowed_celltypes = (
                "plain",
                "float",
                "int",
                "bool",
                "str",
                "binary",
                "text",
            )
            if cell.celltype not in allowed_celltypes:
                msg = "Webunit cells must have celltype in {}. {} has celltype '{}'"
                raise TypeError(msg.format(allowed_celltypes, cell, cell.celltype))
            value = cell.value
            if value is None:
                default = webunit_dict[param].get("default")
                if default is not None:
                    if not cell.independent:
                        print(
                            "WARNING: webunit: skipping default value for empty {}, because it is not independent".format(
                                cell
                            ),
                            file=sys.stderr,
                        )
                    else:
                        cell.set(default)
            share = cell._get_hcell().get("share")
            if share is None:
                readonly = webunit_dict[param].get("readonly", True)
                sharepath = id_ + "/" + webunit_dict[param]["share"]
                print(
                    "webunit: non-shared {}, sharing as '{}'".format(cell, sharepath),
                    file=sys.stderr,
                )
                cell.share(sharepath, readonly=readonly)
            else:
                sharepath = share["path"]
            cells[param] = "/".join(cell._path)

    webcells = webunit_dict.get("@webcells")
    if webcells:
        webcells2 = {}
        for wname, default in webcells.items():
            webcellname = id_ + "_" + wname
            webcells2[webcellname] = default
            cells[wname] = webcellname
        new_webunit["webcells"] = webcells2
    sibling_webunits.append(new_webunit)
    webunits[name] = sibling_webunits
    ctx._graph.params["webunits"] = webunits
    return id_


def add_webunit_template(name: str, webunit_dict: dict[str, Any]) -> None:
    """Adds a new webunit template.
    webunit_dict must be a dict of webunit template parameters.
    They are typically loaded from a .yaml file.
    See the .yaml files in seamless.highlevel.webunits for examples.

    "name" is the name of the webunit template. After calling this function,
    new webunit instances can be constructed using:

    seamless.highlevel.webunits.<name>(ctx, **params)"""
    from .. import Cell, Context

    webunit_dict2 = deepcopy(webunit_dict)
    parameters = [
        Parameter(name="ctx", kind=Parameter.POSITIONAL_OR_KEYWORD, annotation=Context),
    ]
    paramtype = Parameter.POSITIONAL_OR_KEYWORD
    had_default = False
    webcells = {}
    for parname, par in webunit_dict.items():
        if parname == "help":
            continue
        annotation = Parameter.empty
        if par["type"] == "webcell":
            default = par["default"]
            webcells[parname] = default
            webunit_dict2.pop(parname)
            continue
        elif par["type"] == "cell":
            annotation = Cell
            default = Parameter.empty
        elif par["type"] == "value":
            default = par.get("default")
            if "default" not in par:
                default = Parameter.empty
        else:
            raise TypeError("Unknown parameter type for parameter '{}'".format(parname))
        if default is not Parameter.empty:
            had_default = True
        elif had_default:
            paramtype = Parameter.KEYWORD_ONLY
        param = Parameter(parname, paramtype, annotation=annotation, default=default)

        parameters.append(param)
    if len(webcells):
        webunit_dict2["@webcells"] = webcells
    webunit_dict2["@name"] = name
    help = webunit_dict2.pop("help", name)
    func_impl = functools.partial(_add_webunit_instance, webunit_dict=webunit_dict2)
    func = makefun.with_signature(Signature(parameters), func_name=name, doc=help)(
        func_impl
    )
    globals()[name] = func


def _init():
    currdir = os.path.dirname(os.path.abspath(__file__))
    yaml_files = glob.glob("{}/*.yaml".format(currdir))
    result = []
    for yaml_file in yaml_files:
        with open(yaml_file) as f:
            webunit_dict = yaml.load(f.read())
        name = os.path.splitext(os.path.split(yaml_file)[1])[0]
        try:
            add_webunit_template(name, webunit_dict)
        except Exception:
            print("***** ERROR *****", file=sys.stderr)
            print("Webunit template '{}'".format(name), file=sys.stderr)
            traceback.print_exc(limit=0)
            print("*****************", file=sys.stderr)
        result.append(name)
    return result


__all__ = _init() + ["add_webunit_template"]


def __dir__():
    return sorted(__all__)

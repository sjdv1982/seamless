import json
import inspect
import textwrap

from seamless.highlevel.DeepCell import DeepCell

def _get_value(name, value):
    if callable(value):
        value = inspect.getsource(value)
        if value is None:
            raise Exception("Cannot obtain source code for '{}'".format(name))
        value = textwrap.dedent(value)
    return RichValue(value).value

def get_argument_value(name, value):
    if isinstance(value, Cell_like):
        raise TypeError("'%s' is a value argument, you cannot pass a cell" % name)
    elif isinstance(value, Base):
        raise TypeError("'%s' must be value, not '%s'" % (name, type(value)))
    return _get_value(name, value)

def parse_argument(argname, argvalue, parameter, *, parent=None):
    if parent is not None:
        if isinstance(argvalue, Cell_like + (Context, SubContext)):
            if argvalue._parent() is not parent:
                msg = "%s '%s' must belong to the same toplevel Context as the parent"
                raise TypeError(msg % (type(argvalue).__name__, argname))
    par = parameter
    if argvalue is None and par.get("must_be_defined") == False:
        return None
    if par["type"] == "value":
        value = get_argument_value(argname, argvalue)
    elif par["type"] == "context":
        if not isinstance(argvalue, (Context, SubContext)):
            msg = "%s must be Context, not '%s'"
            raise TypeError(msg % (argname, type(argvalue)))
        value = argvalue._path
    elif par["type"] == "cell":
        if not isinstance(argvalue, Cell_like):
            msg = "%s must be Cell-like, not '%s'"
            raise TypeError(msg % (argname, type(argvalue)))
        celltype = par.get("celltype")
        if celltype is not None:
            if argvalue.celltype != celltype:
                msg = "%s must have celltype '%s', not '%s"
                raise TypeError(msg % (argname, celltype, argvalue.celltype))
        value = argvalue._path
    elif par["type"] == "kwargs":
        if isinstance(argvalue, Cell_like):
            value = ("cell", argvalue._path)
        elif isinstance(argvalue, Base):
            raise TypeError("'%s' must be value or cell, not '%s'" % (argname, type(argvalue)))
        else:
            value = ("value", _get_value(argname, argvalue))
    elif par["type"] == "celldict":
        try:
            argvalue.items()
        except Exception:
            raise TypeError((argname, type(argvalue))) from None
        celltype = par.get("celltype")
        value = {}
        for k, v in argvalue.items():
            if not isinstance(k, str):
                msg = "%s must contain string keys, not '%s'"
                raise TypeError(msg % (argname, type(k)))
            if not isinstance(v, Cell_like):
                msg = "%s['%s'] must be Cell-like, not '%s'"
                raise TypeError(msg % (argname, k, type(v)))
            if celltype is not None:
                if v.celltype != celltype:
                    msg = "%s['%s'] must have celltype '%s', not '%s"
                    raise TypeError(msg % (argname, k, celltype, v.celltype))
            value[k] = v._path
    else:
        raise NotImplementedError(par["type"])
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        raise ValueError("Argument '{}' is not JSON-serializable".format(argname)) from None
    return value

from silk.Silk import RichValue
from ..Base import Base
from ..Cell import Cell
from ..DeepCell import DeepCell, DeepFolderCell
from ..Context import Context
from ..SubContext import SubContext
Cell_like = (Cell, DeepCell, DeepFolderCell)
def get_argument_value(name, value):
    if isinstance(value, Cell):
        if value._get_hcell().get("constant"):
            value = value.value
        else:
            raise TypeError("'%s' is a value argument, you cannot pass a cell unless it is constant" % name)
    elif isinstance(value, Base):
        raise TypeError("'%s' must be value or constant cell, not '%s'" % (name, type(value)))
    return RichValue(value).value

def parse_argument(argname, argvalue, parameter):
    par = parameter
    if par["type"] == "value":
        value = get_argument_value(argname, argvalue)
    elif par["type"] == "context":
        if not isinstance(argvalue, (Context, SubContext)):
            msg = "%s must be Context, not '%s'"
            raise TypeError(msg % (argname, type(argvalue)))
        value = argvalue._path
    elif par["type"] == "cell":
        if not isinstance(argvalue, Cell):
            msg = "%s must be Cell, not '%s'"
            raise TypeError(msg % (argname, type(argvalue)))
        celltype = par.get("celltype")
        if celltype is not None:
            if argvalue.celltype != celltype:
                msg = "%s must have celltype '%s', not '%s"
                raise TypeError(msg % (argname, celltype, argvalue.celltype))
        value = argvalue._path
    else:  # par["type"] == "celldict":
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
            if not isinstance(v, Cell):
                msg = "%s['%s'] must be Cell, not '%s'"
                raise TypeError(msg % (argname, k, type(v)))
            if celltype is not None:
                if v.celltype != celltype:
                    msg = "%s['%s'] must have celltype '%s', not '%s"
                    raise TypeError(msg % (argname, k, celltype, v.celltype))
            value[k] = v._path
    return value

from silk.Silk import RichValue
from ..Base import Base
from ..Cell import Cell
from ..Context import Context, SubContext
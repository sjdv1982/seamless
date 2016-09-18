import numpy as np
import weakref
from collections import OrderedDict

_elementaries = {
 "String": str,
 "Integer": int,
 "Float": float,
 "Bool": bool,
}

_minischemas = {}

def register_minischema(minischema):
    typename = minischema.get("type", None)
    assert typename not in _minischemas, typename
    base = minischema.get("base", None)
    dtype = []
    if base is not None:
        baseschema = _minischemas[base]["minischema"]
        minischema0 = baseschema.copy()
        minischema0.update(minischema)
        props = {}
        props.update(baseschema["properties"])
        order = minischema.get("order", baseschema["order"])
        required = minischema.get("required", baseschema["required"])
        props2 = minischema.get("properties", {})
        props.update(props2)
    else:
        order = minischema["order"]
        required = minischema["required"]
        props = minischema["properties"]
    allprops = list(props.keys())
    assert sorted(order) == sorted(allprops), (order, allprops)
    newprops = {}
    for pname in order:
        prop = {}
        prop["composite"] = False
        p = props[pname]
        if isinstance(p, str):
            ptype = p
            p = {"type": p}
        elif "Enum" in p:
            raise NotImplementedError #enum
        elif "properties" in p:
            raise NotImplementedError #composite
        else:
            ptype = p["type"]
        prop["optional"] = (pname in required)
        prop["typename"] = ptype
        if ptype in _elementaries:
            prop["elementary"] = True
            pdtype = _elementaries[ptype]
            if pdtype is float:
                pprecision = p.get("precision", "double")
                if pprecision == "double":
                    pass
                elif pprecision == "single":
                    pdtype = np.float32
                else:
                    raise ValueError(pprecision)
            if pdtype is str:
                plength = p.get("length", 1)
                pdtype = "|S{0}".format(plength)
        else:
            prop["elementary"] = False
            subschema = _minischemas[ptype]
            pdtype = subschema["dtype"]
        dtype.append((pname, pdtype))
        newprops[pname] = prop

    extended_minischema = {
        "typename": typename,
        "minischema": minischema,
        "properties": newprops,
        "order": order,
        "dtype": dtype,
        "base": base,
    }
    if typename is not None:
        _minischemas[typename] = extended_minischema
    else:
        return extended_minischema

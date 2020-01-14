import numpy as np
import weakref
from collections import OrderedDict

from .typenames import _primitives
_elementaries = "float", "int", "str", "bool", "enum"
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
        required = minischema.get("required", baseschema.get("required", None))
        init = minischema.get("init", baseschema.get("init", []))
        props2 = minischema.get("properties", {})
        props.update(props2)
    else:
        order = minischema["order"]
        required = minischema.get("required", None)
        init = minischema.get("init", [])
        props = minischema["properties"]
    allprops = list(props.keys())
    assert sorted(order) == sorted(allprops), (order, allprops)
    newprops = {}

    def _register(pname, prop, p, dtype):
        prop["composite"] = False
        standard_dtype = True
        if isinstance(p, str):
            ptype = p
            p = {"type": p}
        elif "Enum" in p:
            prop["enum"] = tuple(p["Enum"])
            ptype = "enum"
            pdtype = "str"
        elif "properties" in p:
            sub_props = p["properties"]
            sub_order = p.get("order", None)
            if sub_order is None:
                sub_order = sorted(list(sub_order.keys))
            sub_required = p.get("required", None)
            sub_init = p.get("init", [])
            prop["composite"] = True
            prop["order"] = sub_order

            prop["properties"] = {}
            pdtype = []
            sub_optionals = []
            for sub_pname in sub_order:
                sub_prop = {}
                sub_p = sub_props[sub_pname]
                _register(sub_pname, sub_prop, sub_p, pdtype)
                optional = \
                   sub_required is not None \
                   and sub_pname not in sub_required \
                   and sub_pname not in sub_init
                sub_prop["optional"] = optional
                if optional:
                    sub_optionals.append(("HAS_"+sub_pname, np.bool))
                prop["properties"][sub_pname] = sub_prop
            prop["dtype"] = pdtype + sub_optionals
        else:
            ptype = p["type"]
        if not prop["composite"]:
            prop["typename"] = ptype
            if ptype in _primitives:
                prop["elementary"] = True
                pdtype = _primitives[ptype].dtype
            elif ptype in _elementaries:
                prop["elementary"] = True
                if pdtype == "float":
                    pprecision = p.get("precision", "double")
                    if pprecision == "double":
                        pass
                    elif pprecision == "single":
                        pdtype = np.float32
                    else:
                        raise ValueError(pprecision)
                if pdtype in ("str", "enum"):
                    plength = p.get("length", 255)
                    pdtype = "|S{0}".format(plength)
            else:
                prop["elementary"] = False
                if ptype.endswith("Array"):
                    arity = 0
                    while ptype.endswith("Array"):
                        arity += 1
                        ptype = ptype[:-len("Array")]
                    if "maxshape" in prop:
                        if arity == 1:
                            maxshape = int(prop["maxshape"])
                        else:
                            maxshape = np.array(prop["maxshape"], dtype=int)
                            assert len(maxshape.shape) == arity
                            maxshape = tuple(maxshape)
                        subschema = _minischemas[ptype]
                        pdtype = subschema["dtype"]
                        dtype.append((pname, pdtype, maxshape))
                    else:
                        prop["var_array"] = True
                        dtype.append((pname, np.object))
                        dtype.append(("PTR_"+pname, np.uintp))
                    if arity == 1:
                        dtype.append(("LEN_"+pname, np.uint32, (1,)))
                    else:
                        if "maxshape" in prop:
                            dtype.append((
                                "LEN_"+pname, np.bool, maxshape
                            ))
                        else:
                            dtype.append(("LEN_"+pname, np.object))
                            dtype.append(("PTR_LEN_"+pname, np.uintp))
                            dtype.append(("SHAPE_"+pname, np.uint32, arity))
                    standard_dtype = False
                else:
                    subschema = _minischemas[ptype]
                    pdtype = subschema["dtype"]
        if standard_dtype:
            dtype.append((pname, pdtype))

    optionals = []
    for pname in order:
        prop = {}
        p = props[pname]
        _register(pname, prop, p, dtype)
        optional = required is not None \
         and pname not in required \
         and pname not in init
        if optional:
            optionals.append(("HAS_"+pname, np.bool))
        prop["optional"] = optional
        newprops[pname] = prop
    dtype += optionals

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
    return extended_minischema

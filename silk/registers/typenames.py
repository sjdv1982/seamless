import numpy as np
import weakref
from collections import OrderedDict
from ..classes import primitives as _prim
from ..validate import is_valid_silktype

_primitives = {}
for name in _prim.__dict__:
    if is_valid_silktype(name):
        _primitives[name] = getattr(_prim, name)

#TODO:
# - array (1 for 1-dimensional array, 2 for array-array)
# - primitive arrays (in ../classes/primitives.py)

#TODO: Numpy implementation for XArray and String
# no auto-resizing on overflow (a[10] gives an error for |S10) but resize can be requested

_typenames = {}
_typenames.update(_primitives)

from ..classes.silk import Silk
from .minischemas import _minischemas

def register(extended_minischema, init_tree=None, validationblocks=None, errorblocks=None):
    typename = extended_minischema.get("typename", None)
    if validationblocks is not None: raise NotImplementedError
    if errorblocks is not None: raise NotImplementedError
    dtype = extended_minischema["dtype"]
    ms = extended_minischema["minischema"]
    all_props = OrderedDict()
    def fill_props(props, order, msprops):
        for p in order:
            msprop = msprops[p]
            prop = {}
            if msprop["composite"]:
                props[p] = OrderedDict()
                p_order = prop["order"]
                sub_msprops = msprops[p]
                fill_props(props[p], p_order, sub_msprops)
            else:
                prop["optional"] = msprop["optional"]
                prop["elementary"] = msprop["elementary"]
                prop["typename"] = msprop["typename"]
                props[p] = prop
    fill_props(all_props, extended_minischema["order"], extended_minischema["properties"])
    positional_args = []
    first_optional_arg = False
    msprops = extended_minischema["properties"]
    for p in extended_minischema["order"]:
        msprop = msprops[p]
        if msprop["optional"]:
            first_optional_arg = True
        else:
            if first_optional_arg:
                break
        positional_args.append(p)
    d = {
     "_props": all_props,
     "_dtype": dtype,
     "_positional_args": positional_args,
    }
    typename2 = "<Anonymous Silk class>"
    if typename is not None:
        typename2 = typename
    ret = type(typename2, (Silk,), d)
    if typename is not None:
        _typenames[typename] = ret
    return ret

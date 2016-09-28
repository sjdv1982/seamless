import numpy as np
from collections import OrderedDict
from ..classes import primitives as _prim
from ..validate import is_valid_silktype
from .. import exceptions
from .blockmixin import validation_mixin, method_mixin
from ..stringparse import stringparse

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
_silk_types = _typenames.copy() # TODO: primitive arrays
for name in dir(exceptions):
    c = getattr(exceptions, name)
    try:
        if issubclass(c, exceptions.SilkError):
            _silk_types[name] = c
    except TypeError:
        pass

from ..classes.silk import Silk
from .minischemas import _minischemas

_counter = 0
def register(extended_minischema, init_tree=None, \
  validation_blocks=None, error_blocks=None, method_blocks=None):
    global _counter
    _counter += 1
    typename = extended_minischema.get("typename", None)
    ms_props = extended_minischema["properties"]
    typename2 = "<Anonymous Silk class %d>" % (_counter)
    if typename is not None:
        typename2 = typename
    validation_class = None
    if validation_blocks:
        validation_class = validation_mixin(
            typename2,
            validation_blocks,
            error_blocks,
            ms_props,
            _silk_types
        )
    method_class = None
    if method_blocks:
        method_class = method_mixin(
            typename2,
            method_blocks,
            _silk_types
        )

    dtype = extended_minischema["dtype"]
    ms = extended_minischema["minischema"]
    all_props = OrderedDict()
    props_init = {}
    def fill_props(props, order, msprops):
        for p in order:
            msprop = msprops[p]
            prop = OrderedDict()
            props[p] = prop
            initstr = None
            if init_tree is not None and p in init_tree:
                initstr = init_tree[p]
            if msprop["composite"]:
                p_order = msprop["order"]
                sub_msprops = msprops[p]
                fill_props(prop, p_order, sub_msprops)
                if initstr is not None:
                    init = stringparse(initstr, typeless=True )
                    props_init[p] = init
            else:
                prop["elementary"] = msprop["elementary"]
                typename = msprop["typename"]
                typeclass = _typenames[typename]
                prop["typename"] = typename
                if initstr is not None:
                    init = stringparse(initstr, typeless=False)
                    if not isinstance(init, typeclass):
                        init = typeclass(init)
                    props_init[p] = init
            prop["optional"] = msprop["optional"]

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
     "_props_init": props_init,
     "_dtype": dtype,
     "_positional_args": positional_args,
    }
    bases = [method_class, validation_class, Silk]
    bases = [b for b in bases if b is not None]
    ret = type(typename2, tuple(bases), d)
    if typename is not None:
        _typenames[typename] = ret
        _silk_types[typename] = ret # TODO: arrays
    return ret

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
# no auto-resizing on overflow (a[10] gives an error for |S1) but resize can be requested

_typenames = {}
_typenames.update(_primitives)
_silk_types = _typenames.copy()


for name in dir(exceptions):
    c = getattr(exceptions, name)
    try:
        if issubclass(c, exceptions.SilkError):
            _silk_types[name] = c
    except TypeError:
        pass


def _make_array(typename, typeclass, elementary=False):
    from ..classes.silkarray import SilkArray
    typename_array = typename + "Array"
    d = {
      "_element": typeclass,
      "_dtype": typeclass._dtype,
      "_has_optional": typeclass._has_optional,
      "_elementary": elementary,
      "_arity": 1,
    }
    arr = type(typename_array, (SilkArray,), d)
    _silk_types[typename_array] = arr

    typename_array2 = typename + "ArrayArray"
    d = {
      "_element": arr,
      "_dtype": typeclass._dtype,
      "_has_optional": typeclass._has_optional,
      "_elementary": False,
      "_arity": 2,
    }
    arr2 = type(typename_array2, (SilkArray,), d)
    _silk_types[typename_array2] = arr2

    typename_array3 = typename + "ArrayArrayArray"
    d = {
      "_element": arr2,
      "_dtype": typeclass._dtype,
      "_has_optional": typeclass._has_optional,
      "_elementary": False,
      "_arity": 3,
    }
    arr3 = type(typename_array3, (SilkArray,), d)
    _silk_types[typename_array3] = arr3

for name in _primitives:
    if name in ("SilkObject", "SilkStringLike"):
        continue
    _make_array(name, _typenames[name], elementary=True)

_counter = 0
def register(extended_minischema, init_tree=None,
             validation_blocks=None, error_blocks=None, method_blocks=None):
    from ..classes.silk import Silk
    silk_builtin = [p for p in Silk.__dict__.keys() if p not in
                    object.__dict__.keys() and p != "__module__"]

    global _counter
    _counter += 1
    typename = extended_minischema.get("typename", None)
    ms_props = extended_minischema["properties"]
    for p in ms_props:
        msg = "Property '%s' is a builtin Silk attribute/method"
        if p in Silk.__dict__.keys():
            raise TypeError(msg % p)
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
        for p in method_class.__dict__.keys():
            msg = "Attribute/method '%s' is a builtin Silk attribute/method"
            if p in silk_builtin:
                raise TypeError(msg % p)

    dtype = extended_minischema["dtype"]
    ms = extended_minischema["minischema"]
    all_props = OrderedDict()
    props_init = {}
    typedict = {}
    def fill_props(props, order, msprops, typedict):
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
                    init = stringparse(initstr, typeless=True)
                    props_init[p] = init
                typedict[p] = Silk
            else:
                prop["elementary"] = msprop["elementary"]
                ptypename = msprop["typename"]
                ptypeclass = _typenames[ptypename]
                prop["typename"] = ptypename
                if initstr is not None:
                    init = stringparse(initstr, typeless=False)
                    if not isinstance(init, ptypeclass):
                        init = ptypeclass(init)
                    props_init[p] = init
                typedict[p] = ptypeclass
            prop["optional"] = msprop["optional"]

    fill_props(all_props, extended_minischema["order"],
               extended_minischema["properties"], typedict)
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
    d.update(typedict)
    bases = [method_class, validation_class, Silk]
    bases = [b for b in bases if b is not None]
    ret = type(typename2, tuple(bases), d)
    if typename is not None:
        _typenames[typename] = ret
        _silk_types[typename] = ret
        _make_array(typename, ret)

    return ret

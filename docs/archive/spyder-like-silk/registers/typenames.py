import numpy as np
from collections import OrderedDict
from ..classes import primitives as _prim
from ..classes.enum import make_enum
from ..validate import is_valid_silktype
from .. import exceptions
from .blockmixin import validation_mixin, method_mixin
from ..stringparse import stringparse

_primitives = {}
for name in _prim.__dict__:
    if is_valid_silktype(name):
        _primitives[name] = getattr(_prim, name)


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
      "dtype": typeclass.dtype,
      "_elementary": elementary,
      "_arity": 1,
      "__slots__": [],
    }
    arr = type(typename_array, (SilkArray,), d)
    _silk_types[typename_array] = arr

    typename_array2 = typename + "ArrayArray"
    d = {
      "_element": arr,
      "dtype": typeclass.dtype,
      "_elementary": False,
      "_arity": 2,
      "__slots__": [],
    }
    arr2 = type(typename_array2, (SilkArray,), d)
    _silk_types[typename_array2] = arr2

    typename_array3 = typename + "ArrayArrayArray"
    d = {
      "_element": arr2,
      "dtype": typeclass.dtype,
      "_elementary": False,
      "_arity": 3,
      "__slots__": [],
    }
    arr3 = type(typename_array3, (SilkArray,), d)
    _silk_types[typename_array3] = arr3

for name in _primitives:
    if name in ("SilkObject", "SilkStringLike"):
        continue
    _make_array(name, _typenames[name], elementary=True)

_counter = 0
def register(extended_minischema, init_tree=None,
             validation_blocks=None, error_blocks=None, method_blocks=None,
             typename=None):
    from ..classes.silk import Silk
    silk_builtin = [p for p in Silk.__dict__.keys() if p not in
                    object.__dict__.keys() and p not in ("__module__", "__slots__")]

    global _counter
    _counter += 1
    anonymous = False
    if typename is None:
        typename = extended_minischema.get("typename", None)
    else:
        anonymous = True
    ms_props = extended_minischema["properties"]
    for p in ms_props:
        msg = "Property '%s' is a builtin Silk attribute/method"
        if p in Silk.__dict__.keys():
            raise TypeError(msg % p)
    typename2 = "<Anonymous Silk class %d>" % (_counter)
    if typename is not None:
        typename2 = typename
    else:
        anonymous = True
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
                sub_msprops = msprops[p]
                prop["elementary"] = False
                if initstr is not None:
                    init = stringparse(initstr, typeless=True)
                    props_init[p] = init
                sub_typename = None
                if typename is not None:
                    sub_typename = typename + "." + p
                ptypeclass = register(sub_msprops, typename=sub_typename)
                prop["typeclass"] = ptypeclass
                typedict[p] = ptypeclass
            else:
                prop["elementary"] = msprop["elementary"]
                ptypename = msprop["typename"]
                if ptypename == "enum":
                    enum = msprop["enum"]
                    ptypeclass = make_enum(enum)
                    prop["typeclass"] = ptypeclass
                else:
                    ptypeclass = _silk_types[ptypename]
                    prop["typename"] = ptypename
                if initstr is not None:
                    init = stringparse(initstr, typeless=False)
                    if not isinstance(init, ptypeclass):
                        init = ptypeclass(init)
                    props_init[p] = init
                typedict[p] = ptypeclass
            prop["optional"] = msprop["optional"]
            if "var_array" in msprop:
                prop["var_array"] = msprop["var_array"]

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
     "_anonymous": anonymous,
     "_props": all_props,
     "_props_init": props_init,
     "dtype": dtype,
     "_positional_args": positional_args,
     "__slots__": [],
    }
    d.update(typedict)
    bases = [method_class, validation_class, Silk]
    bases = [b for b in bases if b is not None]
    ret = type(typename2, tuple(bases), d)
    if not anonymous:
        _typenames[typename] = ret
        _silk_types[typename] = ret
        _make_array(typename, ret)

    return ret

def unregister(typename):
    if typename not in _silk_types:
        return
    _silk_types.pop(typename)
    def stripped_typename(t):
        while t.endswith("Array"):
            t = t[:-len("Array")]
        return t
    popped = [t for t in _typenames if stripped_typename(t) == typename]
    for t in popped:
        _typenames.pop(t)

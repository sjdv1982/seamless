import numpy as np
from collections import OrderedDict, Counter
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


_typenames = {} # TODO RENAME!!!
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
      "_elementary": elementary,
      "_arity": 1,
      "__slots__": [],
    }
    arr = type(typename_array, (SilkArray,), d)
    _silk_types[typename_array] = arr

    typename_array2 = typename + "ArrayArray"
    d = {
      "_element": arr,
      "_dtype": typeclass._dtype,
      "_elementary": False,
      "_arity": 2,
      "__slots__": [],
    }
    arr2 = type(typename_array2, (SilkArray,), d)
    _silk_types[typename_array2] = arr2

    typename_array3 = typename + "ArrayArrayArray"
    d = {
      "_element": arr2,
      "_dtype": typeclass._dtype,
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

_counter = Counter()


def _fill_props(typename, init_tree, props_init, props, order, msprops, typedict):
    for name in order:
        minischema_prop_data = msprops[name]

        prop = OrderedDict()
        props[name] = prop

        initstr = None

        if init_tree is not None and name in init_tree:
            initstr = init_tree[name]

        if minischema_prop_data["composite"]:
            sub_msprops = msprops[name]
            prop["elementary"] = False
            if initstr is not None:  # currently not used
                init = stringparse(initstr, typeless=True)
                props_init[name] = init

            sub_typename = None
            if typename is not None:
                sub_typename = typename + "." + name

            prop_type_class = register(sub_msprops, typename=sub_typename)
            prop["typeclass"] = prop_type_class
            typedict[name] = prop_type_class

        else:
            prop["elementary"] = minischema_prop_data["elementary"]
            prop_type_name = minischema_prop_data["typename"]
            if prop_type_name == "enum":
                enum = minischema_prop_data["enum"]
                prop_type_class = make_enum(enum)
                prop["typeclass"] = prop_type_class

            else:
                prop_type_class = _silk_types[prop_type_name]
                prop["typename"] = prop_type_name

            if initstr is not None:
                init = stringparse(initstr, typeless=False)
                if not isinstance(init, prop_type_class):
                    init = prop_type_class(init)

                props_init[name] = init

            typedict[name] = prop_type_class

        prop["optional"] = minischema_prop_data["optional"]
        if "var_array" in minischema_prop_data:
            prop["var_array"] = minischema_prop_data["var_array"]


def register(extended_minischema, init_tree=None, validation_blocks=None, error_blocks=None, method_blocks=None,
             typename=None):

    from ..classes.silk import Silk
    silk_builtin = [p for p in Silk.__dict__.keys() if p not in
                    object.__dict__.keys() and p not in ("__module__", "__slots__")]
    anonymous = False
    if typename is None:
        typename = extended_minischema.get("typename", None)
    else:
        anonymous = True

    ms_props = extended_minischema["properties"]
    for name in ms_props:
        msg = "Property '%s' is a builtin Silk attribute/method"
        if name in Silk.__dict__.keys():
            raise TypeError(msg % name)

    typename2 = "<Anonymous Silk class %d>" % (next(_counter))
    if typename is not None:
        typename2 = typename

    else:
        anonymous = True

    validation_class = None
    if validation_blocks:
        validation_class = validation_mixin(typename2, validation_blocks, error_blocks, ms_props, _silk_types)

    method_class = None
    if method_blocks:
        method_class = method_mixin(typename2, method_blocks, _silk_types )
        for name in method_class.__dict__.keys():
            msg = "Attribute/method '%s' is a builtin Silk attribute/method"
            if name in silk_builtin:
                raise TypeError(msg % name)

    dtype = extended_minischema["dtype"]
    all_props = OrderedDict()
    props_init = {}
    type_dict = {}

    _fill_props(typename, init_tree, props_init, all_props,
                extended_minischema["order"], extended_minischema["properties"], type_dict)
    positional_args = []

    minischema_props = extended_minischema["properties"]
    for name in extended_minischema["order"]:
        minischema_prop_data = minischema_props[name]

        positional_args.append(name)
        if minischema_prop_data["optional"]:
            break

    cls_dict = {"_anonymous": anonymous, "_props": all_props, "_props_init": props_init, "_dtype": dtype,
                "_positional_args": positional_args, "__slots__": []}
    cls_dict.update(type_dict)

    bases = [method_class, validation_class, Silk]
    bases = [b for b in bases if b is not None]

    type_class = type(typename2, tuple(bases), cls_dict)

    if not anonymous:
        _typenames[typename] = type_class
        _silk_types[typename] = type_class
        _make_array(typename, type_class)

    return type_class

import numpy as np
import weakref
from collections import OrderedDict


def _get_primitive_type_float(schema_prop):
    float_precision = schema_prop.get("precision", "double")
    primitive_data_type = float

    if float_precision == "double":
        pass

    elif float_precision == "single":
        primitive_data_type = np.float32

    else:
        raise ValueError(float_precision)

    return primitive_data_type


def _get_primitive_type_str(schema_prop):
    prop_length = schema_prop.get("length", 1)
    primitive_data_type = "|S{0}".format(prop_length)
    return primitive_data_type


_primitive_type_info = {
 "String": (str, _get_primitive_type_str),
 "Integer": (int, lambda schema_prop: int),
 "Float": (float, _get_primitive_type_float),
 "Bool": (bool, lambda schema_prop: bool),
}
_minischemas = {}
_typeclasses = {}


def todo(*args, **kwargs):
    raise NotImplementedError


def register_minischema(minischema):
    name = minischema["type"]
    assert name not in _minischemas, name
    base = minischema.get("base", None)
    if base is not None:
        raise NotImplementedError

    data_types = []
    order = minischema["order"]
    minischema_properties = minischema["properties"]
    all_prop_names = list(minischema_properties.keys())
    assert sorted(order) == sorted(all_prop_names), (order, all_prop_names)

    props = {}
    for prop_name in order:
        prop = {}
        schema_prop = minischema_properties[prop_name]

        # If schema property is a single string, reconstruct the formal dict {'type': ...}
        if isinstance(schema_prop, str):
            prop_type = schema_prop
            schema_prop = {"type": schema_prop}

        else:
            prop_type = schema_prop["type"]

        prop["optional"] = schema_prop.get("optional", False)

        if prop_type in _primitive_type_info:
            prop["elementary"] = True
            primitive_class, primitive_data_type_getter = _primitive_type_info[prop_type]
            prop["typeclass"] = primitive_class
            primitive_data_type = primitive_data_type_getter(schema_prop)

        else:
            prop["elementary"] = False
            prop["typeclass"] = _typeclasses[prop_type]
            subschema = _minischemas[prop_type]
            primitive_data_type = subschema["dtype"]

        data_types.append((prop_name, primitive_data_type))
        props[prop_name] = prop

    _minischemas[name] = {
        "minischema": minischema,
        "properties": props,
        "dtype": data_types,
        "base": base,
    }
    _typeclasses[name] = todo


#TODO: Numpy implementation for XArray and String
# no auto-resizing on overflow (a[10] gives an error for |S10) but resize can be requested

class BaseClass:
    __slots__ = "_parent", "_storage", "_data", "_children"

    def __dir__(self):
        return list(self._props)

    def __getattr__(self, attr):
        try:
            prop = self._props[attr]

        except KeyError:
            raise AttributeError(attr)

        is_elementary = ["elementary"]

        if is_elementary:
            return self._data[attr]

        else:
            return self._children[attr]

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)

        else:
            try:
                prop = self._props[attr]

            except KeyError:
                raise AttributeError(attr)

            is_elementary = ["elementary"]
            if is_elementary:
                self._data[attr] = value

            else:
                self._children[attr]._set(value)

class NumpyClass:
    _npclassname = "NumpyClass"

    def __init__(self, parent, data):
        classname = self._npclassname

        if parent is not None:
            self._parent = weakref.ref(parent)

        else:
            self._parent = lambda: None

        self._data = data
        self._children = {}

        for name, prop in self._props.items():
            if prop["elementary"]:
                continue

            some_obj = prop["typeclass"]
            data_type_class = getattr(some_obj, classname)
            self._children[name] = data_type_class(self, data[name])


class NumpyMaskClass(NumpyClass):
    _npclassname = "NumpyMaskClass"

    def __getattr__(self, attr):
        value = super(NumpyMaskClass, self).__getattr__(attr)
        if value is np.ma.masked:
            return None

        return value

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)

        else:
            try:
                prop = self._props[attr]

            except KeyError:
                raise AttributeError(attr)

            is_elementary = prop["elementary"]
            if is_elementary:
                if value is None:
                    value = np.ma.masked

                self._data[attr] = value

            else:
                self._children[attr]._set(value)


def make_baseclass(name, silk_definition):
    dtype = silk_definition["dtype"]
    ms = silk_definition["minischema"]
    props = OrderedDict()
    order = ms["order"]

    for prop_name in order:
        silk_prop = silk_definition["properties"][prop_name]
        prop = {"optional": silk_prop["optional"],
                "elementary": silk_prop["elementary"],
                "typeclass": silk_prop["typeclass"]
                }

        props[prop_name] = prop

    cls_dict = {
     "_props": props,
     "_dtype": dtype,
    }

    return type(name, (BaseClass,), cls_dict)

"""
class SilkMetaBase(type):
    def __instancecheck__(cls, instance):
        #... compare instance.SilkDefinitionClass with cls.SilkDefinitionClass
    def __subclasscheck__(cls, subclass):
        #... compare instance.SilkDefinitionClass with cls.SilkDefinitionClass

def build_silkclass(name, silk_definition):
    classdict = _classdict.copy()
    silk_baseclass = make_baseclass(name, silk_definition)
    classdict["SilkBaseClass"] = silk_baseclass
    classdict["SilkDefinitionClass"] = silk_definitionclass #TODO: make from code block
    classdict["JSONClass"] = numpy_class(silk_definition, silk_baseclass, silk_definitionclass)
    classdict["NumpyClass"] = json_class(silk_definition, silk_baseclass, silk_definitionclass)
    base = silk_definition["base"]
    if base is None:
        bases = (silk_baseclass,)
    else:
        bases = (silk_baseclass, base)
    return SilkMetaBase(name,bases,classdict)
"""

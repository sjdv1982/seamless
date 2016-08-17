import numpy as np
import weakref
from collections import OrderedDict

_primitives = {
 "String": str,
 "Integer": int,
 "Float": float,
 "Bool": bool,
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
    dtype = []
    order = minischema["order"]
    allprops = list(minischema["properties"].keys())
    assert sorted(order) == sorted(allprops), (order, allprops)
    props = {}
    for pname in order:
        prop = {}
        p = minischema["properties"][pname]
        if isinstance(p, str):
            ptype = p
            p = {"type": p}
        else:
            ptype = p["type"]
        prop["optional"] = p.get("optional", False)
        if ptype in _primitives:
            prop["elementary"] = True
            ptypeclass = _primitives[ptype]
            prop["typeclass"] = ptypeclass
            pdtype = ptypeclass
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
            prop["typeclass"] = _typeclasses[ptype]
            subschema = _minischemas[ptype]
            pdtype = subschema["dtype"]
        dtype.append((pname, pdtype))
        props[pname] = prop

    _minischemas[name] = {
        "minischema": minischema,
        "properties": props,
        "dtype": dtype,
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
            ele = self._props[attr]["elementary"]
        except KeyError:
            raise AttributeError(attr)
        if ele:
            return self._data[attr]
        else:
            return self._children[attr]

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)
        else:
            try:
                ele = self._props[attr]["elementary"]
            except KeyError:
                raise AttributeError(attr)
            if ele:
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
        for pname, p in self._props.items():
            if p["elementary"]:
                continue
            t = p["typeclass"]
            tt = getattr(t, classname)
            self._children[pname] = tt(self, data[pname])

class NumpyMaskClass(NumpyClass):
    _npclassname = "NumpyMaskClass"
    def __getattr__(self, attr):
        d = super(NumpyMaskClass, self).__getattr__(attr)
        if d is np.ma.masked:
            return None
        else:
            return d
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)
        else:
            try:
                ele = self._props[attr]["elementary"]
            except KeyError:
                raise AttributeError(attr)
            if ele:
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
    for p in order:
        sdprop = silk_definition["properties"][p]
        prop = {}
        prop["optional"] = sdprop["optional"]
        prop["elementary"] = sdprop["elementary"]
        prop["typeclass"] = sdprop["typeclass"]
        props[p] = prop
    d = {
     "_props": props,
     "_dtype": dtype,
    }
    return type(name, (BaseClass,), d)

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

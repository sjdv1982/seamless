from numpy import void
from abc import MutableMapping
from . import MixedBase, Scalar, _array_types, build_form, build_form_numpy

class MixedDict(MixedBase,  MutableMapping):
    def __init__(self, data, form = None, parent = None):
        self._parent = parent  #Propagate form changes to parent!!!
        if isinstance(data, MixedDict):
            self._data = data._data
            self._form = data._form
        else:
            if form is None:
                form = self._build_form(data)
            self._data = data
            self._form = form

    def _build_form(self, data):
        if isinstance(data, Scalar):
            raise TypeError
        elif isinstance(data, void):
            dt = data.dtype
            storage, type_ = build_form_numpy(dt)
        elif isinstance(data, _array_types):
            raise TypeError
        elif isinstance(data, dict):
            type_ = {}
            storages = set()
            for k,v in data.items():
                cstorage, ctypedef = build_form(data)
                type_[k] = ctype_
                storages.add(cstorage)
            all_plain = all([s == "pure-plain" for s in storages])
            if all_plain:
                storage = "pure-plain"
            else:
                storage = "mixed-plain"
            return storage, typedef
        else:
            raise TypeError
        return storage, typedef

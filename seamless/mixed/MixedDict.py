from numpy import void
from collections.abc import MutableMapping
from . import MixedBase, Scalar, _array_types
from .get_form import get_form_dict

class MixedDict(MixedBase,  MutableMapping):
    def __init__(self, data, form = None, parent = None):
        self._parent = parent  #Propagate form changes to parent!!!
        if isinstance(data, MixedDict):
            self._data = data._data
            self._form = data._form
        else:
            if form is None:
                form = get_form_dict(data)
            self._data = data
            self._form = form

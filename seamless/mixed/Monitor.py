from numpy import ndarray, void
from .get_form import get_form
from . import MixedScalar, MixedBase, Scalar,  scalars, is_np_struct, _allowed_types
from . import MonitorTypeError
from .Backend import Backend
import json
from copy import deepcopy
from .. import Wrapper

class Monitor:
    def __init__(self, backend):
        assert isinstance(backend, Backend)
        self.backend = backend

    def get_instance(self, subform, path):
        if subform is None:
            if len(path):
                raise KeyError(path)
            return MixedObject(self, path)
        if isinstance(subform, str):
            type_ = subform
        else:
            type_ = subform["type"]
        if type_ == "object":
            if subform.get("storage","pure-plain").endswith("binary"):
                return MixedNumpyStruct(self, path)
            else:
                return MixedDict(self, path)
        elif type_ == "array":
            if subform.get("storage","pure-plain").endswith("binary"):
                return MixedNumpyArray(self, path) #ndarray has an immutable type
            else:
                return MixedList(self, path)
        elif type_ in scalars:
            return MixedScalar(self, path) #scalars are all immutable
        else:
            raise TypeError(type_)

    def _get_path(self, path):
        subdata = self.backend.get_path(path)
        subform = self.backend.get_subform(path)
        return subdata, subform

    def get_path(self, path=()):
        subdata, subform = self._get_path(path)
        return self.get_instance(subform, path)

    def get_data(self, path=()):
        subdata, subform = self._get_path(path)
        return subdata

    def get_form(self, path=()):
        subdata, subform = self._get_path(path)
        return subform

    def get_storage(self, path=()):
        if not len(path):
            return self.backend.get_storage()
        if len(path) == 1:
            parent_storage = self.backend.get_storage()
            if parent_storage is None:
                raise AttributeError(path)
        else:
            parent_subdata, parent_subform = self._get_path(path[:-1])
            if parent_subform is None:
                raise AttributeError(path)
            parent_storage = parent_subform.get("storage")
            if parent_storage is None:
                if isinstance(parent_subdata, (void, ndarray)):
                    parent_storage = "pure-binary"
                else:
                    parent_storage = "pure-plain"
        subdata, subform = self._get_path(path)
        storage = None
        if isinstance(subform, dict):
            storage = subform.get("storage")
        if storage is None:
            if parent_storage.endswith("binary"):
                return "pure-binary"
            else:
                return "pure-plain"
        else:
            return storage

    def set_path(self, path, subdata):
        if isinstance(subdata, MixedBase):
            subdata = subdata.value
        if not isinstance(subdata, _allowed_types):
            raise TypeError(type(subdata))
        if self.backend.plain:
            json.dumps(subdata)
        self.backend.set_path(path, subdata)

    def insert_path(self, path, subdata):
        """
        Inserts subdata right before the insertion point "path"
        The insertion point must be a list item
        """
        if not isinstance(subdata, _allowed_types):
            raise TypeError(type(subdata))
        if not len(path):
            raise TypeError
        if not isinstance(path[-1], int):
            raise TypeError(path)
        if self.backend.plain:
            json.dumps(subdata)
        self.backend.insert_path(path, subdata)

    def del_path(self, path):
        self.backend.del_path(path)

    def __str__(self):
        return str(self.get_path())

    def __repr__(self):
        return repr(self.get_path())

from .MixedObject import MixedObject
from .MixedDict import MixedDict, MixedNumpyStruct
from .MixedList import MixedList, MixedNumpyArray

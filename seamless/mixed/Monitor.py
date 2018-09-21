from numpy import ndarray, void
from .get_form import get_form
from . import MixedScalar, MixedBase, Scalar,  scalars, is_np_struct, _allowed_types
from . import MonitorTypeError
import json
from copy import deepcopy

def get_subpath(data, form, path):
    if data is None or silk.is_none(data):
        return None, None, None
    if isinstance(form, str):
        type_ = form
    else:
        type_ = form["type"]
    if not len(path):
        assert type_ in scalars
        result = data, form, None
        return result
    attr = path[0]
    if type_ == "object":
        assert isinstance(attr, str), attr
        if attr not in data:
            return None, None, None
        subdata = data[attr]
        subform = form["properties"][attr]
        result = subdata, subform, None
        return result
    elif type_ in ("array", "tuple"):
        assert isinstance(attr, int), attr
        assert attr >= 0
        if len(data) <= attr:
            return None, None, None
        subdata = data[attr]
        if form["identical"]:
            subform = form["items"]
        else:
            subform = form["items"][attr]
        result = subdata, subform, None
        return result
    elif type_ in scalars:
        raise MonitorTypeError
    else:
        raise TypeError(type_)

class Monitor:
    _data_update_hook = None
    _form_update_hook = None
    def __init__(self, data, storage, form, *, attribute_access=False, plain=False, **kwargs):
        self.attribute_access = attribute_access #does the underlying data support data.attr instead of just data["attr"]?
            #(even if true, only supported for attrs that do not start with _, and are not list/dict attrs/methods)
        if "data_hook" in kwargs:
            self._data_hook = kwargs["data_hook"]
        self.data = data
        if plain:
            assert storage is None
        else:
            if storage is None:
                assert "storage_hook" in kwargs
            self.storage = storage
        if "storage_hook" in kwargs:
            self._storage_hook = kwargs["storage_hook"]
        self.plain = plain
        if form is None:
            assert "form_hook" in kwargs
        if "form_hook" in kwargs:
            self._form_hook = kwargs["form_hook"]
        if "data_update_hook" in kwargs:
            self._data_update_hook = kwargs["data_update_hook"]
        if "form_update_hook" in kwargs:
            self._form_update_hook = kwargs["form_update_hook"]
        self.form = form
        self.pathcache = {} #path cache; key is a path. value consist of a tuple:
        # (subdata, subform, trigger) where trigger is None or (triggertype, parentpath)
        # triggertype can be "storage" or "identical"
        # "storage" trigger means that the storage of the parentpath could be changed if the path storage changes
        # "identical" trigger means that the parentpath could change from "identical" to non-identical
        # TODO, triggers. For now, just recalculate the entire form on every change

    def get_instance(self, subform, subdata, path):
        if subdata is None or silk.is_none(subdata):
            if not len(path):
                assert self._data_hook is not None
            if self._data_hook is not None:
                return MixedObject(self, path)
            else:
                return None
        if isinstance(subform, str):
            type_ = subform
        else:
            type_ = subform["type"]
        if type_ == "object":
            if isinstance(subdata, void) and subform.get("storage") == "pure-binary":
                return MixedNumpyStruct(self, path)
            else:
                return MixedDict(self, path)
        elif type_ == "array":
            if isinstance(subdata, ndarray) and subform.get("storage") == "pure-binary":
                return MixedNumpyArray(self, path) #ndarray has an immutable type
            else:
                return MixedList(self, path)
        elif type_ in scalars:
            return MixedScalar(self, path) #scalars are all immutable
        else:
            raise TypeError(type_)

    def _get_parent_path(self, path, child_data):
        return self._get_path(path[:-1])

    def _get_path(self, path):
        if not len(path):
            result = self.data, self.form, None
            return result
        result = self.pathcache.get(path)
        if result is None:
            subdata, subform = self.data, self.form
            start = 0
            for start in range(len(path)-1, 0, -1):
                cached_path = path[:start]
                part_result = self.pathcache.get(cached_path)
                if part_result is not None:
                    subdata, subform, _ = part_result
                    break
            else:
                start = 0
            for n in range(start, len(path)):
                cached_path = path[:n+1]
                remaining_path = path[n:]
                part_result = get_subpath(subdata, subform, remaining_path)
                self.pathcache[cached_path] = part_result #TODO: restore
                subdata, subform, _ = part_result
            result = part_result
        return result

    def get_path(self, path=()):
        subdata, subform, trigger = self._get_path(path)
        return self.get_instance(subform, subdata, path)

    def get_data(self, path=()):
        subdata, subform, trigger = self._get_path(path)
        return subdata

    def get_form(self, path=()):
        subdata, subform, trigger = self._get_path(path)
        return subform

    def get_storage(self, path=()):
        if self.plain:
            return "pure-plain"
        if not len(path):
            return self.storage
        if len(path) == 1:
            parent_storage = self.storage
        else:
            parent_subdata, parent_subform, _ = self._get_path(path[:-1])
            parent_storage = parent_subform.get("storage")
            if parent_storage is None:
                if isinstance(parent_subdata, (void, ndarray)):
                    parent_storage = "pure-binary"
                else:
                    parent_storage = "pure-plain"
        subdata, subform, _ = self._get_path(path)
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

    def set_path(self, path, subdata, **kwargs):
        """
        Updates the data under path with the value "subdata"
        Then, updates the form
        """
        if isinstance(subdata, MixedBase):
            subdata = subdata.value
        if not isinstance(subdata, _allowed_types):
            raise TypeError(type(subdata))
        if self.plain:
            json.dumps(subdata)
        if not len(path):
            _, form = get_form(subdata)
            if form is None:
                type_ = None
            if isinstance(form, str):
                type_ = form
                if type_ == "null":
                    type_ = None
            else:
                type_ = form["type"]
            if type_ == "object":
                if isinstance(self.data, dict) and isinstance(subdata, dict):
                    self.data.clear()
                    self.data.update(subdata)
                elif isinstance(self.data, void) and isinstance(subdata, void):
                    arr = np.array(self.data)
                    arr[0] = subdata
                else:
                    self.data = self._data_hook(subdata)
                    #raise TypeError(type_, type(self.data), type(subdata))
            elif type_ == "array":
                if isinstance(self.data, list) and isinstance(subdata, list):
                    self.data[:] = subdata
                elif isinstance(self.data, ndarray) and isinstance(subdata, ndarray):
                    if self.data.shape != subdata.shape:
                        self.data = self._data_hook(subdata)
                        #raise TypeError(self.data.shape, subdata.shape)
                    else:
                        self.data[:] = subdata
                else:
                    self.data = self._data_hook(subdata)
                    #raise TypeError(type_, type(self.data), type(subdata))
            elif type_ is None or type_ in scalars:
                self.data = self._data_hook(subdata)
            else:
                raise TypeError(type_)
            self.recompute_form(data=subdata)
        else:
            parent_subdata, parent_subform, trigger = self._get_parent_path(path, subdata)
            if isinstance(parent_subform, str):
                type_ = parent_subform
            else:
                type_ = parent_subform["type"]
            attr = path[-1]
            if type_ == "object":
                assert isinstance(attr, str), attr
                parent_subdata[attr] = subdata
            elif type_ in ("array", "tuple"):
                assert isinstance(attr, int), attr
                parent_subdata[attr] = subdata
            elif type_ in scalars:
                raise TypeError(type_)
            else:
                raise TypeError(type_)
        if self._data_update_hook is not None:
            self._data_update_hook()
        self.recompute_form(path)

    def recompute_form(self, subpath=None, data=None):
        """
        TODO: use triggers for efficiency, based on subpath
        For now, just update the data and recompute the entire form
        """
        self.pathcache.clear()
        if data is None:
            data = self.data
        storage, form = get_form(data)
        if self.form is None or subpath is None:
            self.form = self._form_hook(form)
        else:
            if isinstance(self.form, dict):
                self.form.clear()
                self.form.update(form)
            elif isinstance(self.form, list):
                self.form[:] = form
            else:
                self._form_hook(form)
        if not self.plain:
            if self.storage is None or self.storage != storage:
                self.storage = storage
                self._storage_hook(storage)
        if self._form_update_hook is not None:
            self._form_update_hook()

    def insert_path(self, path, subdata):
        """
        Inserts subdata right before the insertion point "path"
        The insertion point must be a list item
        Then, updates the form
        TODO: use triggers for efficiency
        For now, just update the data and recompute the entire form
        """
        if not isinstance(subdata, _allowed_types):
            raise TypeError(type(subdata))
        if not len(path):
            raise TypeError
        if not isinstance(path[-1], int):
            raise TypeError(path)

        parent_subdata, parent_subform, trigger = self._get_path(path[:-1])
        if isinstance(parent_subform, str):
            type_ = parent_subform
        else:
            type_ = parent_subform["type"]
        item = path[-1]
        if type_ == "object":
            raise TypeError(type_)
        elif type_ == "tuple":
            raise TypeError(type_)
        elif type_ == "array":
            assert isinstance(item, int), item
            parent_subdata.insert(item, subdata)
        elif type_ in scalars:
            raise TypeError(type_)
        else:
            raise TypeError(type_)
        self.recompute_form(path)

    def del_path(self, path):
        """
        Deletes the data under path
        Then, updates the form
        TODO: use triggers for efficiency
        For now, just update the data and recompute the entire form
        """
        if not len(path):
            raise TypeError
        else:
            parent_subdata, parent_subform, trigger = self._get_path(path[:-1])
            type_ = parent_subform["type"]
            attr = path[-1]
            if type_ == "object":
                assert isinstance(attr, str), attr
                parent_subdata.pop(attr)
            elif type_ == "array":
                assert isinstance(attr, str), int
                if isinstance(self.data, ndarray):
                    raise TypeError #cannot remove items from ndarray
                self.data.pop(attr)
            elif type_ == "tuple":
                raise TypeError(type_)
            elif type_ in scalars:
                raise TypeError(type_)
            else:
                raise TypeError(type_)
        self.recompute_form(path)

    def _monitor_get_state(self):
        memo = {}
        data = deepcopy(self.data, memo)
        if self.plain:
            storage = "pure-plain"
        else:
            storage = deepcopy(self.storage, memo)
        form = deepcopy(self.form, memo)
        return data, storage, form

    def _monitor_set_state(self, state):
        data, storage, form = state
        if self._data_hook is not None:
            self.data = self._data_hook(data)
        else:
            self.data = data
        if self.plain:
            assert storage == "pure-plain"
        else:
            if self._storage_hook is not None:
                self.storage = self._storage_hook(storage)
            else:
                self.storage = storage
        if self._form_hook is not None:
            self.form = self._form_hook(form)
        else:
            self.form = form
        self.pathcache.clear()


from .MixedObject import MixedObject
from .MixedDict import MixedDict, MixedNumpyStruct
from .MixedList import MixedList, MixedNumpyArray
from .. import silk

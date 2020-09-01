from copy import deepcopy
from collections import defaultdict

from .get_form import get_form as calc_form

def get_subform(form, path):
    if not len(path):
        return form
    if form is None:
        return None
    attr = path[0]
    if isinstance(form, str):
       return None
    type_ = form["type"]
    if type_ == "object":
        assert isinstance(attr, str), attr
        if "properties" not in form:
            return None
            #raise ValueError(form)
            #pass
        if attr not in form["properties"]:
            return None
        subform = form["properties"][attr]
    elif type_ in ("array", "tuple"):
        assert isinstance(attr, int), attr
        if attr < 0:
            items = form["items"]
            attr = len(items) + attr
        if form["identical"]:
            subform = form["items"]
        else:
            items = form["items"]
            if attr >= len(items):
                return None
            subform = form["items"][attr]
    elif type_ in scalars:
        return None
    else:
        raise TypeError(type_)
    return get_subform(subform, path[1:])


class Backend:
    formless = False
    toplevel_dataclass = None
    def __init__(self, plain):
        self._plain = plain

    @property
    def plain(self):
        return self._plain

    def get_subform(self, path):
        for pp in path:
            assert isinstance(pp, (int, str))
        form = self.get_form()
        return get_subform(form, path)

    def set_path(self, path, data):
        for pp in path:
            assert isinstance(pp, (int, str))
        if data is None:
            return self.del_path(path)
        for start in range(len(path)-1):
            subpath = path[:start]
            subdata = self.get_path(subpath)
            if subdata is None:
                break
        else:
            start = len(path) - 1
        for n in range(start, len(path)-1):
            p = path[n]
            if isinstance(p, int):
                d = []
            else:
                d = {}
            self._set_path(path[:n], d)
        self._set_path(path, data)

        if not len(path) or start == len(path) - 1:
            newdata = data
            newpath = path
        else:
            newpath = path[:start+1]
            newdata = self.get_path(newpath)
        storage, form = calc_form(newdata)
        self._set_form(form, newpath)
        if self.plain:
            assert storage == "pure-plain", storage
        else:
            if not len(path):
                self._set_storage(storage)
        self._update(path)

    def del_path(self, path):
        for pp in path:
            assert isinstance(pp, (int, str))
        if not len(path):
            self._del_path(())
            return
        subdata = self.get_path(path[:-1])
        if subdata is None:
            return
        subform, substorage = self._get_form(path[:-1])
        if isinstance(subform, str):
            subformtype = subform
        else:
            subformtype = subform["type"]
        attr = path[-1]
        if isinstance(attr, int):
            if subformtype != "array":
                raise TypeError(subform) #must be "array"
            if substorage.endswith("binary"):
                raise TypeError #cannot remove items from binary
            self._del_path(path)
        else:
            if subformtype != "object":
                raise TypeError(subform) #must be "object"
            self._del_path(path)
        self._update(path)

    def insert_path(self, path, data):
        for pp in path:
            assert isinstance(pp, (int, str))
        attr = path[-1]
        if not isinstance(attr, int):
            raise TypeError(path)
        subdata = self.get_path(path[:-1])
        if subdata is None:
            self.set_path(path[:-1], [])
        subform, storage = self._get_form(path[:-1])
        if isinstance(subform, str):
            subformtype = subform
            substorage = "pure-plain"
        else:
            subformtype = subform["type"]
            substorage = subform.get("storage", storage)
        if subformtype != "array":
            raise TypeError(subform) #must be "array"
        if substorage.endswith("binary"):
            raise TypeError #cannot insert items in binary
        self._insert_path(data, path)
        self._update(path)

class DefaultBackend(Backend):
    def __init__(self, plain, *, data_getter=None, data_setter=None):
        super().__init__(plain)
        self._data = None
        self._form = None
        self._storage = None
        self._data_getter = data_getter
        self._data_setter = data_setter

    def get_storage(self):
        if self._plain:
            return "pure-plain"
        assert isinstance(self._storage, (str, type(None)))
        return self._storage

    def _set_storage(self, value):
        if self._plain:
            raise AttributeError
        assert isinstance(value, (str, type(None)))
        self._storage = value

    def get_data(self):
        if self._data_getter is not None:
            return self._data_getter()
        else:
            return self._data

    def get_form(self):
        return self._form

    def get_path(self, path):
        for pp in path:
            assert isinstance(pp, (int, str))
        data = self.get_data()
        if not len(path):
            return data
        result = data
        for p in path:
            if result is None:
                return None
            if isinstance(p, int):
                if p >= len(result):
                    return None
            result = result[p]
        return result

    def _set_path(self, path, data):
        if not len(path):
            if self._data_setter is not None:
                self._data_setter(data)
            else:
                self._data = deepcopy(data)
            return
        subdata = self.get_path(path[:-1])
        attr = path[-1]
        if isinstance(attr, int):
            if attr >= len(subdata):
                assert isinstance(subdata, list), type(subdata)
                for n in range(len(subdata), attr + 1):
                    subdata.append(None)
        subdata[attr] = data

    def _insert_path(self, data, path):
        subdata = self.get_path(path[:-1])
        attr = path[-1]
        assert isinstance(attr, int)
        assert isinstance(subdata, list)
        if len(subdata) >= attr:
            for n in range(len(subdata), attr+1):
                subdata.append(None)
            subdata[attr] = data
        else:
            subdata.insert(attr, data)

    def _del_path(self, path):
        if not len(path):
            if self._data_setter is not None:
                self._data_setter(None)
            else:
                self._data = None
            return
        subdata = self.get_path(path[:-1])
        attr = path[-1]
        subdata.pop(attr)

    def _get_form(self, path):
        if not len(path):
            return self.get_form(), self.get_storage()
        subform, substorage = self._get_form(path[:-1])
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                subform2 = subform["items"]
            else:
                subform2 = subform["items"][attr]
        else:
            subform2 = subform["properties"][attr]
        if "storage" in subform2:
            substorage = subform2["storage"]
        return subform2, substorage

    def _set_form(self, form, path):
        if not len(path):
            self._form = deepcopy(form)
            return
        subform, _ = self._get_form(path[:-1])
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                subform["items"] = form
            else:
                subform["items"][attr] = form
        else:
            if "properties" not in subform:
                subform["properties"] = {}
            subform["properties"][attr] = form

    def _update(self, path):
        data = self.get_data()
        storage, form = calc_form(data)
        if self.plain:
            assert storage == "pure-plain", storage
        else:
            self._set_storage(storage)
            self._form = form

class SilkBackend(DefaultBackend):
    _silk = None
    def __init__(self):
        super().__init__(plain=False)

    def set_silk(self, silk):
        from ..silk.Silk import Silk
        if not isinstance(silk, Silk):
            raise TypeError("silk")
        self._silk = silk

    def _update(self, path):
        super()._update(path)
        assert self._silk is not None
        data = self._silk
        for item in path:
            data = data._getitem(item)
        data.validate(full=None)

class StructuredCellBackend(Backend):
    def __init__(self, structured_cell):
        self._structured_cell = structured_cell
        super().__init__(False)
        self._calc_form()

    @property
    def formless(self):
        return self._structured_cell.hash_pattern is not None

    @property
    def toplevel_dataclass(self):
        sc = self._structured_cell
        if sc.hash_pattern is None:
            return None
        elif sc.hash_pattern == {"*": "#"}:
            return dict
        elif sc.hash_pattern == {"!": "#"}:
            return list
        else:
            raise NotImplementedError(sc.hash_pattern)


    def _calc_form(self):
        sc = self._structured_cell
        if sc.hash_pattern is not None:
            self._storage = None
            self._form = None
        else:
            data = self.get_data()
            storage, form = calc_form(data)
            if form == "null":
                form = None
            self._storage = storage
            self._form = form

    def get_storage(self):
        if self._plain:
            return "pure-plain"
        assert isinstance(self._storage, (str, type(None)))
        return self._storage

    def _set_storage(self, value):
        if self._plain:
            raise AttributeError
        assert isinstance(value, (str, type(None)))
        self._storage = value

    def get_data(self):
        return self._structured_cell._get_auth_path(())

    def get_form(self):
        return self._form

    def get_path(self, path):
        return self._structured_cell._get_auth_path(path)

    def _set_path(self, path, data):
        sc = self._structured_cell
        if not len(path):
            sc._set_auth_path((), data)
            return
        probe_sub = False
        if sc.hash_pattern is None:
            probe_sub = True
        else:
            if sc.hash_pattern == {"*": "#"}:
                if len(path) == 1:
                    if sc._auth_none():
                        sc._set_auth_path((), {})
                else:
                    probe_sub = True
            elif sc.hash_pattern == {"!": "#"}:
                if len(path) == 1:
                    if sc._auth_none():
                        sc._set_auth_path((), [])
                else:
                    probe_sub = True
            else:
                raise NotImplementedError(sc.hash_pattern)
        if probe_sub:
            subdata = self.get_path(path[:-1])
            attr = path[-1]
            subpath = path[:-1]
            if subdata is None:
                if isinstance(attr, int):
                    sc._set_auth_path(path[:-1], [])
                else:
                    sc._set_auth_path(path[:-1], {})
                subdata = self.get_path(path[:-1])
            if isinstance(attr, int):
                if attr >= len(subdata):
                    assert isinstance(subdata, list), type(subdata)
                    for n in range(len(subdata), attr):
                        sc._set_auth_path(subpath + (n,), None)
        sc._set_auth_path(path, data)

    def _insert_path(self, data, path):
        raise NotImplementedError # StructuredCell Silk wrapper does not support insertion

    def _del_path(self, path):
        sc = self._structured_cell
        sc._set_auth_path(path, None)

    def _get_form(self, path):
        if not len(path):
            return self.get_form(), self.get_storage()
        subform, substorage = self._get_form(path[:-1])
        if subform is None:
            return subform, substorage
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                subform2 = subform["items"]
            else:
                subform2 = subform["items"][attr]
        else:
            subform2 = subform["properties"][attr]
        if "storage" in subform2:
            substorage = subform2["storage"]
        return subform2, substorage

    def _set_form(self, form, path):
        if not len(path):
            if form == "null":
                form = None
            self._form = deepcopy(form)
            return
        subform, _ = self._get_form(path[:-1])
        if subform is None:
            return
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                subform["items"] = form
            else:
                subform["items"][attr] = form
        else:
            if "properties" not in subform:
                subform["properties"] = {}
            subform["properties"][attr] = form

    def _update(self, path):
        self._calc_form()
        sc = self._structured_cell
        sc._join()

class StructuredCellSchemaBackend(StructuredCellBackend):
    def __init__(self, structured_cell):
        self._structured_cell = structured_cell
        Backend.__init__(self, True)
        self._storage = "pure-plain"
        data = self.get_data()
        if data is None:
            ### self.set_path((), {}) # .set_path can be async!
            data = {}
        storage, form = calc_form(data)
        assert storage == "pure-plain"
        self._form = form

    def get_storage(self):
        return "pure-plain"

    def _set_storage(self, value):
        raise AttributeError

    def get_data(self):
        return self._structured_cell._get_schema_path(())

    def get_path(self, path):
        return self._structured_cell._get_schema_path(path)

    def _set_path(self, path, data):
        sc = self._structured_cell
        if not len(path):
            sc._set_schema_path((), data)
            return
        subdata = self.get_path(path[:-1])
        attr = path[-1]
        subpath = path[:-1]
        if isinstance(attr, int):
            if attr >= len(subdata):
                assert isinstance(subdata, list), type(subdata)
                for n in range(len(subdata), attr):
                    sc._set_schema_path(subpath + (n,), None)
        sc._set_schema_path(path, data)

    def _insert_path(self, data, path):
        raise NotImplementedError # StructuredCell Silk wrapper does not support insertion

    def _del_path(self, path):
        sc = self._structured_cell
        sc._set_schema_path(path, None)

    def _update(self, path):
        sc = self._structured_cell
        data = self.get_data()
        _, form = calc_form(data)
        self._form = form
        sc._join_schema()

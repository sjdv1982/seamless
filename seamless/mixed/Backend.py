from copy import deepcopy

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
        if attr not in form["properties"]:
            return None
        subform = form["properties"][attr]
    elif type_ in ("array", "tuple"):
        assert isinstance(attr, int), attr
        assert attr >= 0
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

    def insert_path(self, data, path):
        for pp in path:
            assert isinstance(pp, (int, str))        
        attr = path[-1]
        if not isinstance(attr, int):
            raise TypeError(path)
        subdata = self.get_path(path[:-1])
        if subdata is None:
            self.set_path(path[:-1], [])
        subform = self._get_form(path[:-1])
        if isinstance(subform, str):
            subformtype = subform
            substorage = "pure-plain"
        else:
            subformtype = subform["type"]
            substorage = subform["storage"]
        if subformtype != "array":
            raise TypeError(subform) #must be "array" 
        if substorage.endswith("binary"):
            raise TypeError #cannot insert items in binary
        self._insert_path(data, path)
        self._update(path)

class DefaultBackend(Backend):
    def __init__(self, plain):
        super().__init__(plain)
        self._data = None
        self._form = None
        self._storage = None

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
        self._storage = storage
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
        data = self.get_data()
        storage, form = calc_form(data)
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
        if not len(path):
            self._data = deepcopy(data)
            return
        subdata = self.get_path(path[:-1])
        attr = path[-1]
        sc = self._structured_cell
        subpath = path[:-1]
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
        self._storage = storage
        self._form = form
        sc = self._structured_cell
        sc._join()

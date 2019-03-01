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
            return False
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
        subform = self._get_form(path[:-1])
        if isinstance(subform, str):
            subformtype = subform
            substorage = "pure-plain"
        else:
            subformtype = subform["type"]
            substorage = subform["storage"]
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

class DefaultBackend(Backend):
    def __init__(self, plain):
        super().__init__(plain)
        self._data = None
        self._form = None
        self._storage = None

    def get_storage(self):
        if self._plain:
            return "pure-plain"
        return self._storage

    def _set_storage(self, value):
        if self._plain:
            raise AttributeError
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
            assert isinstance(subdata, list)
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
            return self.get_form()
        subform = self._get_form(path[:-1])
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                return subform["items"]
            else:
                return subform["items"][attr]
        else:
            return subform["properties"][attr]

    def _set_form(self, form, path):
        if not len(path):
            self._form = deepcopy(form)
            return
        subform = self._get_form(path[:-1])
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
        # TODO: proper form re-calculation
        # for now, it doesn't work (since a storage change may propagate upstream)
        data = self.get_data()
        storage, form = calc_form(data)
        self._storage = storage
        self._form = form



class CellBackend(Backend):
    def __init__(self, cell):
        from ..core.cell import MixedCell, PlainCell
        assert isinstance(cell, (MixedCell, PlainCell))
        plain = (isinstance(cell, PlainCell))
        super().__init__(plain)
        self._cell = cell
        self._tempdata = None
        self._tempform = None
        self._tempstorage = None
        self._updated_paths = set()
        self._deleted_paths = set()

    def get_storage(self):
        if self._plain:
            return "pure-plain"
        return self._cell.storage

    def _set_storage(self, value):
        if self._plain:
            raise AttributeError
        self._tempstorage = value

    def get_data(self):
        return self._cell.data

    def get_form(self):
        return self._cell.form

    def get_path(self, path):
        data = self.get_data()
        return self._get_path(path, data)

    def _get_path(self, path, data):
        for pp in path:
            assert isinstance(pp, (int, str))
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
        self._updated_paths.add(tuple(path))
        if not len(path):
            self._tempdata = deepcopy(data)
            return
        elif self._tempdata is None:
            self._tempdata = deepcopy(self._cell.data)
        subdata = self._get_path(path[:-1], self._tempdata)
        attr = path[-1]
        if isinstance(attr, int):
            assert isinstance(subdata, list)
            for n in range(len(subdata), attr + 1):
                subdata.append(None)
        subdata[attr] = data

    def _insert_path(self, data, path):
        if self._tempdata is None:
            self._tempdata = deepcopy(self._cell.data)
        prepath = tuple(path[:-1])
        subdata = self._get_path(prepath, self._tempdata)
        attr = path[-1]
        assert isinstance(attr, int)
        assert isinstance(subdata, list)
        if len(subdata) >= attr:
            for n in range(len(subdata), attr+1):
                path2 = prepath + (n,)
                self._updated_paths.add(path2)
                subdata.append(None)            
            subdata[attr] = data
        else:
            subdata.insert(attr, data)
        self._updated_paths.add(tuple(path))
        
    def _del_path(self, path):
        if not len(path):
            self._tempdata = None
            return
        elif self._tempdata is None:
            self._tempdata = deepcopy(self._cell.data)
        subdata = self._get_path(path[:-1], self._tempdata)
        attr = path[-1]
        subdata.pop(attr)
        self._deleted_paths.add(tuple(path))

    def _get_form(self, path):
        if self._tempform is None:
            self._tempform = deepcopy(self._cell.form)
        if not len(path):
            return self._tempform
        subform = self._get_form(path[:-1])
        attr = path[-1]
        if isinstance(attr, int):
            if subform["identical"]:
                return subform["items"]
            else:
                return subform["items"][attr]
        else:
            return subform["properties"][attr]

    def _set_form(self, form, path):
        if not len(path):
            self._tempform = deepcopy(form)
            return
        subform = self._get_form(path[:-1])
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
        # TODO: proper form re-calculation
        # for now, it doesn't work (since a storage change may propagate upstream)
        assert not len(self._updated_paths) or not len(self._deleted_paths) # update OR delete
        if len(self._deleted_paths):
            deleted = True
            updated = self._deleted_paths
        else:
            deleted = False
            updated = self._updated_paths
        updated2 = set()
        for path in updated:
            for n in range(len(path)):
                p = path[:n]
                if p not in updated:
                    updated2.add(p)
        # TODO: make a meaningful distinction between updated and updated2
        # updated have independent values, whereas updated2 only changed b/c of children
        # This makes only sense with cache tree depth
        updated = updated.union(updated2)
        data = self._tempdata
        self._tempdata = None
        self._tempform = None
        self._tempstorage = None
        self._updated_paths.clear()
        self._cell.set(data) # will also compute storage and form
        manager = self._cell._get_manager()
        ccache = manager.cell_cache
        cell = self._cell
        for path in sorted(updated, key=lambda p:len(p)):
            auth = ccache.cell_to_authority[cell][path]
            has_auth = (auth != False)
            manager._update_status(
                self._cell, (not deleted), 
                has_auth=has_auth, origin=None,
                cell_subpath=path
            )
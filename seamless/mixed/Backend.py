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
        self._modified_paths = {}

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
            try:
                result = result[p]
            except (KeyError, TypeError, IndexError, AttributeError):
                return None
        return result

    def _set_path(self, path, data):
        self._modified_paths[tuple(path)] = False
        if not len(path):
            self._tempdata = deepcopy(data)
            return
        elif self._tempdata is None:
            self._tempdata = deepcopy(self._cell.data)
        subdata = self._get_path(path[:-1], self._tempdata)
        attr = path[-1]

        if subdata is None and len(path) == 1:
            if isinstance(attr, int):
                self.set_path((), [])
            else:
                self.set_path((), {})
            return self._set_path(path, data)

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
                self._modified_paths[path2] = False
                subdata.append(None)            
            subdata[attr] = data
        else:
            subdata.insert(attr, data)
        self._modified_paths[tuple(path)] = False
        
    def _del_path(self, path):
        if not len(path):
            self._tempdata = None
            return
        elif self._tempdata is None:
            self._tempdata = deepcopy(self._cell.data)
        subdata = self._get_path(path[:-1], self._tempdata)
        attr = path[-1]
        subdata.pop(attr, None)
        self._modified_paths[tuple(path)] = True


    def _get_form(self, path):
        if self._tempform is None:
            self._tempform = deepcopy(self._cell.form)
        if not len(path):
            return self._tempform, self._tempstorage
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
            self._tempform = deepcopy(form)
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
        # TODO: proper form re-calculation
        # for now, it doesn't work (since a storage change may propagate upstream)
        data = self._tempdata
        DEBUG = False
        self._tempdata = None
        self._tempform = None
        self._tempstorage = None        
        self._cell.set(data) # will also compute storage and form
        manager = self._cell._get_manager()
        ccache = manager.cell_cache
        cell = self._cell
        auths = ccache.cell_to_authority[cell]        
        authkeys = [p for p in auths if p is not None]
        updated_paths = set()
        
        path_is_none = set()
        for path, deleted in self._modified_paths.items():
            if deleted:
               for n in range(len(path)):
                   path_is_none.add(path[:n])
            else:
                updated_paths.add(path)
        cache = {}
        updated_auths = set()
        updated_parent_paths = set()
        for path in updated_paths:
            for n in range(len(path)):
                updated_parent_paths.add(path[:n])
        if DEBUG:
            print("BACKEND DEBUG")
            print("DATA", str(data)[:80])
        for path in sorted(authkeys, key=lambda p:len(p)):
            done = False
            if path in updated_parent_paths:
                updated_auths.add(path)
                continue
            for n in range(len(path)+1):
                if DEBUG > 1:
                    print("NONE?", path, n, path[:n], path_is_none)
                if path[:n] in path_is_none:
                    path_is_none.add(path)
                    done = True
                    break
            if DEBUG > 1:
                print("DONE?", path, done)
            if done:
                continue
            for n in range(len(path)+1):
                if DEBUG > 1:
                    print("UP?", path, n, path[:n], updated_paths)
                if path[:n] in updated_paths:
                    done = True
                    break
            if done:                
                for n in range(len(path)+1):
                    subpath = path[:n]
                    v = cache.get(subpath)
                    if DEBUG > 1:
                        print(path, n, subpath, str(v)[:50])
                    if v is None:
                        v = self.get_path(subpath)
                        if v is None:
                            path_is_none.add(subpath)
                            break
                        else:
                            cache[subpath] = v
                else:
                    if path not in path_is_none:
                        updated_auths.add(path)
                continue            

        if DEBUG:
            print("UPDATED PATHS", updated_paths)
            print("UPDATED AUTHS", updated_auths)
            print("PATH_IS_NONE", path_is_none)               
            print("/BACKEND DEBUG") 
        for path in auths:
            authstatus = None
            if path in updated_auths:
                authstatus = True
            elif path in path_is_none:
                authstatus = False
            if authstatus is None:
                continue
            auth = auths[path]
            has_auth = (auth != False)            
            manager._update_status(
                self._cell, authstatus, 
                has_auth=has_auth, origin=None,
                cell_subpath=path, delay=True
            )
            
        self._modified_paths.clear()
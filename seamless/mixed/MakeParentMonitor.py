from .Monitor import Monitor
from . import _allowed_types, scalars
from numpy import ndarray, void

def get_subpath_insert(data, form, remaining_path):
    type_ = form["type"]
    if not len(path):
        assert type_ in scalars
        result = data, form, None
        return False, result
    attr = path[0]
    if type_ == "object":
        assert isinstance(attr, str), attr
        try:
            subdata = data[attr]
        except AttributeError:
            data[attr] = subdata
            return True, None
        subform = form["properties"][attr]
        result = subdata, subform, None
        return False, result
    elif type_ in ("array", "tuple"):
        assert isinstance(attr, int), attr
        if type_ == "tuple":
            subdata = data[attr]
        else:
            try:
                subdata = data[attr]
            except IndexError:
                assert attr >= 0, attr
                for n in range(len(data), attr):
                    data.append(None)
                data.append(subdata)
                return True, None
        if form["identical"]:
            subform = form["items"]
        else:
            subform = form["items"][attr]
        result = subdata, subform, None
        return False, result
    elif type_ in scalars:
        raise TypeError
    else:
        raise TypeError(type_)

class MakeParentMonitor(Monitor):
    """Subclass of Monitor that inserts non-existing parent paths when paths are set
    NOTE: unlike the standard Monitor, MakeParentMonitor can be initialized with
     data is None. The first path assigment sets it to the correct type
    TODO: some mechanism to pass this new .data on to the cell that holds it
    """

    def _get_parent_path(self, path, subdata):
        if self.data is None:
            if len(path):
                first = path[0]
                if isinstance(first, attr):
                    self.data = {}
                elif isinstance(first, int):
                    self.data = []
            else:
                self.data = subdata
            self.pathcache.clear()
            self.storage, self.form = get_form(self.data)

        parent_path = path[:-1]
        if not len(parent_path):
            result = self.data, self.form, None
            return result
        result = self.pathcache.get(parent_path)
        if result is None:
            subdata, subform = self.data, self.form
            start = 0
            for start in range(len(parent_path)-1, 0, -1):
                cached_path = parent_path[:start]
                part_result = self.pathcache.get(cached_path)
                if part_result is not None:
                    subdata, subform, _ = part_result
                    break
            for n in range(start, len(parent_path)):
                cached_path = parent_path[:n+1]
                remaining_path = parent_path[n:]
                inserted, part_result = get_subpath_insert(subdata, subform, remaining_path)
                if inserted:
                    # We had to insert a parent value => restart
                    #TODO: something less crude...
                    self.pathcache.clear()
                    self.storage, self.form = get_form(self.data)
                    return self._get_parent_path(path, subdata)
                self.pathcache[cached_path] = part_result
                subdata, subform, _ = part_result
            result = part_result
        return result

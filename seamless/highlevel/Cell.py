import weakref
class Cell:
    def __init__(self, parent, path):
        self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

    def __str__(self):
        return str(self._get_cell())

    def _get_cell(self):
        parent = self._parent()
        p = parent._ctx.translated
        for subpath in self._path:
            p = getattr(p, subpath)
        return p

    def _get_hcell(self):
        parent = self._parent()
        return parent._graph[0][self._path]

    @property
    def value(self):
        cell = self._get_cell()
        return cell.value

    @value.setter
    def value(self, value):
        #TODO: check if source cell!!
        #TODO: disable warning!!
        cell = self._get_cell()
        cell.value = value
        hcell = self._get_hcell()
        hcell["value"] = value

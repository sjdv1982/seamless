import weakref

from .Cell import Cell

class SubCell(Cell):
    def __init__(self, parent, cell, subpath, readonly):
        assert not parent._dummy #cannot access cell.attr in constructors, use cell.value.attr instead
        fullpath = cell._path + subpath
        super().__init__(parent, fullpath)
        self._cell = weakref.ref(cell)
        self._readonly = readonly
        self._subpath = subpath

    def _get_hcell(self):
        return self._cell()._get_hcell()

    def _get_cell_subpath(self, cell, subpath):
        return cell

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        from .assign import assign_to_subcell
        parent = self._parent()
        path = self._subpath + (attr,)
        assign_to_subcell(self, path, value)
        ctx = parent._gen_context
        ###if parent._as_lib is not None:
        ###    parent._as_lib.needs_update = True
        parent._translate()

    def __getattr__(self, attr):
        if attr == "value":
            raise AttributeError
        parent = self._parent()
        readonly = self._readonly
        return SubCell(self._parent(), self._cell(), self._subpath + (attr,), readonly=readonly)

    @property
    def authoritative(self):
        #TODO: determine if the subcell didn't get any inbound connections
        # If it did, you can't get another inbound connection, nor a link
        return True #stub

    @property
    def links(self):
        #TODO: return the other partner of all Link objects with self in it
        return [] #stub

    def traitlet(self):
        return self._parent()._add_traitlet(self._cell()._path, self._subpath)

    @property
    def value(self):
        cell = self._cell()
        cellvalue = cell.value
        for attr in self._subpath:
            cellvalue = getattr(cellvalue, attr)
        return cellvalue

    def set(self, value):
        assert not self._readonly
        print("UNTESTED SubCell.set")
        cell = self._cell()
        attr = self._subpath[-1]
        if len(self._subpath) == 1:
            return setattr(cell, attr, value)
        else:
            parent_subcell = SubCell(self._parent(), cell, self._subpath[:-1], False)
            return setattr(parent_subcell, attr, value)

    @property
    def _virtual_path(self):
        cell = self._cell()
        p = cell._virtual_path
        if p is None:
            return None
        return p + self._subpath

    def _set_observers(self):
        pass


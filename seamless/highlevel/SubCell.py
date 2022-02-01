import weakref

from .Cell import Cell

class SubCell(Cell):
    def __init__(self, parent, cell, subpath, readonly):
        assert isinstance(cell, Cell)
        assert not isinstance(cell, SubCell)
        fullpath = cell._path + subpath
        super().__init__(parent=parent, path=fullpath)
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
        assign_to_subcell(self._cell(), path, value)

    def __getattr__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
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

    @property
    def value(self):
        cell = self._cell()
        cellvalue = cell.value
        if cellvalue.unsilk is None:
            raise ValueError
        for attr in self._subpath:
            if isinstance(attr, int):
                cellvalue = cellvalue[attr]
            else:
                cellvalue = getattr(cellvalue, attr)
        return cellvalue

    def set(self, value):
        assert not self._readonly
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

    def __str__(self):
        return "Seamless SubCell: %s" % ".".join(self._path)


class DeepSubCell(SubCell):

    def __init__(self, parent, cell, attr, readonly):
        assert isinstance(cell, DeepCell)
        assert not isinstance(cell, SubCell)
        fullpath = cell._path + (attr,)
        Cell.__init__(self, parent=parent, path=fullpath)
        self._cell = weakref.ref(cell)
        self._readonly = readonly
        self._attr = attr
        self._subpath = (attr,)

    def __getattr__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        raise AttributeError

    @property
    def value(self):
        cell = self._cell()
        celldata = cell.data
        if celldata is None:
            return None
        attr = self._attr
        if isinstance(attr, int):
            if len(celldata) <= attr:
                return None
            checksum = celldata[attr]
        else:
            checksum = getattr(celldata, attr)
        return self._parent().resolve(checksum, "mixed")

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        raise AttributeError(attr)

    def __str__(self):
        return "Seamless DeepSubCell: %s" % ".".join(self._path)

from .DeepCell import DeepCell

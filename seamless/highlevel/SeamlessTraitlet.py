import traitlets
import weakref

class SeamlessTraitlet(traitlets.HasTraits):
    value = traitlets.Instance(object)
    _updating = False
    path = None
    subpath = None
    parent = None
    seamless_cell = None
    def _connect(self):
        from .Cell import Cell
        from ..core import StructuredCell, Cell as core_cell
        hcell = self.parent()._children[self.path]
        if not isinstance(hcell, Cell):
            raise NotImplementedError(type(hcell))
        cell = hcell._get_cell()
        self.seamless_cell = weakref.ref(cell)
        if isinstance(cell, StructuredCell):
            subpath = self.subpath
            if not (subpath is None or subpath == ()):
                raise NotImplementedError(subpath)
        elif isinstance(cell, core_cell):
            assert self.subpath is None
        else:
            raise TypeError(cell)
        print("traitlet %s:%s, observing" % (self.path, self.subpath))        
        cell._add_traitlet(self)

    def receive_update(self, checksum):        
        from ..core import StructuredCell
        value = None
        if checksum is not None:
            cell = self.seamless_cell()
            if cell is None:
                return
            manager = cell._get_manager()
            celldata = cell
            if isinstance(cell, StructuredCell):
                celldata = cell.data
            accessor = manager.get_default_accessor(celldata)
            accessor.subpath = self.subpath
            expression = accessor.to_expression(bytes.fromhex(checksum))
            value = manager.get_expression(expression)
            if value is not None and isinstance(value, tuple):
                value = value[2]
        #print("Traitlet RECEIVE UPDATE", self.path, self.subpath, value)

        self._updating = True
        old_value = self.value
        self.value = value
        # For some mysterious reason, traitlets observers are not notified...
        self._notify_trait("value", old_value, value)
        self._updating = False

    @traitlets.observe('value')
    def _value_changed(self, change):
        if self.parent is None:
            return
        #print("Traitlet DETECT VALUE CHANGE", self.path, self.subpath, change, self._updating)
        if self._updating:
            return
        value = change["new"]
        if isinstance(value, tuple):
            value = list(value)
        hcell = self.parent()._children[self.path]
        handle = hcell
        if self.subpath is not None:
            for p in self.subpath:
                handle = getattr(handle, p)
        handle.set(value)

    def _add_notifiers(self, handler, name, type):
        super()._add_notifiers(handler, name, type)
        try:
            v = getattr(self, name)
        except:
            v = None
        self._notify_trait(name, v, v)

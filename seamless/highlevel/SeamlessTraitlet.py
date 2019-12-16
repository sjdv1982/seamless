import traitlets
import weakref

class SeamlessTraitlet(traitlets.HasTraits):
    value = traitlets.Instance(object)
    _updating = False
    path = None
    parent = None
    seamless_cell = None
    def _connect(self):
        from .Cell import Cell
        from ..core import StructuredCell, Cell as core_cell
        hcell = self.parent()._children[self.path]
        if not isinstance(hcell, Cell):
            raise NotImplementedError(type(hcell))
        cell = hcell._get_cell()
        if hcell.celltype == "structured":
            cell = cell._data
        assert isinstance(cell, core_cell)
        self.seamless_cell = weakref.ref(cell)
        #print("traitlet %s, observing" % self.path)        
        cell._add_traitlet(self)

    def receive_update(self, checksum): 
        assert checksum is not None
        value = None
        manager = self.parent()._manager
        raise NotImplementedError # livegraph branch, feature E4
        # TODO: get buffer from buffer cache, then deserialize...
        accessor = manager.get_default_accessor(celldata)
        expression = accessor.to_expression(bytes.fromhex(checksum))
        value = manager.get_expression(expression)
        if value is not None and isinstance(value, tuple):
            value = value[2]
        #print("Traitlet RECEIVE UPDATE", self.path, value)

        self._updating = True
        old_value = self.value
        self.value = value
        # For some mysterious reason, traitlets observers are not notified...
        self._notify_trait("value", old_value, value)
        self._updating = False

    def _notify_trait(self, name, old_value, new_value):
        if new_value is None:
            return
        super()._notify_trait(name, old_value, new_value)

    @traitlets.observe('value')
    def _value_changed(self, change):
        if self.parent is None:
            return
        #print("Traitlet DETECT VALUE CHANGE", self.path, change, self._updating)
        if self._updating:
            return
        value = change["new"]
        cell = self.seamless_cell()
        cell.set(value)

    def _add_notifiers(self, handler, name, type):
        super()._add_notifiers(handler, name, type)
        try:
            v = getattr(self, name)
        except Exception:
            v = None
        self._notify_trait(name, v, v)

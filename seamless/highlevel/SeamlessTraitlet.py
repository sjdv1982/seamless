import traitlets
from traitlets.traitlets import _validate_link
import weakref
import contextlib

class Link(object):
    """Link traits from different objects together so they remain in sync.
    
    Adapted from the link class in from the traitlets package.
    Will not update on None values

    Parameters
    ----------
    source : (object / attribute name) pair
    target : (object / attribute name) pair

    Examples
    --------

    >>> c = link((src, 'value'), (tgt, 'value'))
    >>> src.value = 5  # updates other objects as well
    """
    updating = False

    def __init__(self, source, target, bidirectional):
        _validate_link(source, target)        
        self.source, self.target = source, target
        self.bidirectional = bidirectional
        source_value = getattr(source[0], source[1])
        try:
            if source_value is not None:
                setattr(target[0], target[1], source_value)
        finally:            
            source[0].observe(
                self._update_target, names=source[1]
            )            
            if bidirectional:
                target[0].observe(
                    self._update_source, names=target[1]
                )

    @contextlib.contextmanager
    def _busy_updating(self):
        self.updating = True
        try:
            yield
        finally:
            self.updating = False

    def _update_target(self, change):
        if self.updating:
            return
        new_value = change.new
        if new_value is None:
            return
        with self._busy_updating():
            setattr(self.target[0], self.target[1], 
                    new_value)

    def _update_source(self, change):
        if self.updating:
            return
        new_value = change.new
        if new_value is None:
            return
        with self._busy_updating():
            setattr(self.source[0], self.source[1], 
                    new_value)

    def unlink(self):
        self.source[0].unobserve(self._update_target, names=self.source[1])
        if self.bidirectional:
            self.target[0].unobserve(self._update_source, names=self.target[1])
            self.source, self.target = None, None

    def __del__(self):
        self.unlink()

class SeamlessTraitlet(traitlets.HasTraits):
    value = traitlets.Instance(object, allow_none=False)
    _destroyed = False
    _updating = False
    parent = None
    cell = None
    def _connect_seamless(self):
        hcell = self.parent()._children[self.path]
        if not isinstance(hcell, Cell):
            raise TypeError(type(hcell))
        if hcell._get_hcell()["celltype"] == "structured":
            raise Exception("%s must be simple cell for traitlet" % cell)
        cell = hcell._get_cell()
        if not isinstance(cell, core_cell):
            raise TypeError(type(cell))
        self.cell = weakref.ref(cell)
        #print("traitlet %s, observing" % self.path)        
        cell._add_traitlet(self)
        self.links = []

    def receive_update(self, checksum): 
        if self._destroyed:
            return
        assert checksum is not None
        value = None
        cell = self.cell()
        if cell._destroyed:
            return
        manager = self.parent()._manager
        buffer_cache = manager.cachemanager.buffer_cache
        buffer = buffer_cache.get_buffer(checksum)
        celltype = cell._celltype
        value = deserialize_sync(
            buffer, checksum, celltype,
            copy=True
        )
        if celltype == "mixed":
            hash_pattern = cell._hash_pattern
            if hash_pattern is not None:
                value = get_subpath(
                    value, hash_pattern, ()
                )
        #print("Traitlet RECEIVE UPDATE", self.path, value)

        self._updating = True
        old_value = self.value
        self.value = value
        self._updating = False

    def _notify_trait(self, name, old_value, new_value):
        if self._destroyed:
            return
        if new_value is None:
            return
        super()._notify_trait(name, old_value, new_value)

    @traitlets.observe('value')
    def _value_changed(self, change):
        if self._destroyed:
            return
        if self.parent is None:
            return
        #print("Traitlet DETECT VALUE CHANGE", self.path, change, self._updating)
        if self._updating:
            return
        value = change["new"]
        if self.cell is None:
            return
        cell = self.cell()
        cell.set(value)

    def _add_notifiers(self, handler, name, type):
        super()._add_notifiers(handler, name, type)
        try:
            v = getattr(self, name)
        except Exception:
            v = None
        self._notify_trait(name, v, v)

    def _connect_traitlet(self, target, target_attr, bidirectional):
        if not isinstance(target, traitlets.HasTraits):
            raise TypeError(type(target))
        if not isinstance(target_attr, str):
            raise TypeError(target_attr)
        target_expr = (target, target_attr)
        source_expr = (self, "value")
        return Link(source_expr, target_expr, bidirectional)
    
    def connect(self, target, target_attr="value"):
        link = self._connect_traitlet(target, target_attr, False)
        self.links.append(link)
        return link

    def link(self, target, target_attr="value"):
        link = self._connect_traitlet(target, target_attr, True)
        self.links.append(link)
        return link

    def destroy(self):
        self._destroyed = True
        self.links.clear()
        parent = self.parent()
        traitlet = parent._traitlets[self.path]
        if traitlet is self:
            parent._traitlets.pop(self.path)


from .Cell import Cell
from ..core.cell import Cell as core_cell
from ..core.protocol.deserialize import deserialize_sync
from ..core.protocol.expression import get_subpath

import traitlets
from traitlets.traitlets import _validate_link
import weakref
import contextlib
import asyncio

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
        if self.source is None:
            return
        self.source[0].unobserve(self._update_target, names=self.source[1])
        if self.bidirectional:
            if self.target is None:
                return
            self.target[0].unobserve(self._update_source, names=self.target[1])
        self.source, self.target = None, None

    def __del__(self):
        self.unlink()

class SeamlessTraitlet(traitlets.HasTraits):
    value = traitlets.Instance(object, allow_none=False)
    _destroyed = False
    _updating = False
    parent = None
    incell = None
    outcell = None
    links = None
    celltype = None
    mimetype = None
    _timer_handle = None

    def _connect_seamless(self):
        ccell = self.parent()._children[self.path]
        if not isinstance(ccell, Cell):
            raise TypeError(type(ccell))
        cell = ccell._get_cell()
        hcell = ccell._get_hcell()
        if hcell["celltype"] == "structured":
            incell = cell
            outcell = cell._data
        else:
            incell, outcell = cell, cell
        old_celltype = self.celltype
        old_mimetype = self.mimetype
        self.celltype = hcell["celltype"]
        self.mimetype = hcell.get("mimetype", None)
        if incell is not None:
            if not isinstance(incell, (core_cell, StructuredCell)):
                raise TypeError(type(incell))
            self.incell = weakref.ref(incell)
        if outcell is not None:
            if not isinstance(outcell, core_cell):
                raise TypeError(type(outcell))
            self.outcell = weakref.ref(outcell)
        #print("traitlet %s, observing" % self.path)
        outcell._add_traitlet(self)
        if old_celltype is not None:
            if self.celltype != old_celltype or self.mimetype != old_mimetype:
                try:
                    self._notify_trait("value", self.value, self.value)
                finally:
                    self._updating = False
                if self.links is not None:
                    self.links = []
        if self.links is not None and not self.incell().has_authority():
            for link in list(self.links):
                if link.bidirectional:
                    print("Removed bidirectional link")
                    link.unlink()
                    self.links.remove(link)

    def receive_update(self, checksum):
        if self._destroyed:
            return
        assert checksum is not None
        value = None
        cell = self.outcell()
        if cell._destroyed:
            return
        manager = self.parent()._manager
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

        if self._timer_handle is not None:
            self._timer_handle.cancel()
            self._timer_handle = None

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
        if self.incell is None:
            return
        cell = self.incell()
        if cell.has_authority():
            if self._timer_handle is not None:
                self._timer_handle.cancel()
            self._timer_handle = asyncio.get_event_loop().call_later(
                0.1,
                self._cell_set,
                cell,
                value,
            )

    def _cell_set(self, cell, value):
        if cell.has_authority():
            cell.set(value)

    def _add_notifiers(self, handler, name, type):
        super()._add_notifiers(handler, name, type)
        try:
            v = getattr(self, name)
        except Exception:
            v = None
        try:
            self._updating = True
            self._notify_trait(name, v, v)
        finally:
            self._updating = False

    def _connect_traitlet(self, target, target_attr, bidirectional):
        if not isinstance(target, traitlets.HasTraits):
            raise TypeError(type(target))
        if not isinstance(target_attr, str):
            raise TypeError(target_attr)
        target_expr = (target, target_attr)
        source_expr = (self, "value")
        return Link(source_expr, target_expr, bidirectional)

    def _newlink(self, link):
        if self.links is None:
            self.links = []
        self.links.append(link)

    def connect(self, target, target_attr="value"):
        link = self._connect_traitlet(target, target_attr, False)
        self._newlink(link)
        return link

    def link(self, target, target_attr="value"):
        if self.incell is not None:
            assert self.incell().has_authority()
        link = self._connect_traitlet(target, target_attr, True)
        self._newlink(link)
        return link

    def observe(self, handler, names=traitlets.All, type='change'):
        super().observe(handler, names, type)
        names = traitlets.parse_notifier_name(names)
        if names == [traitlets.All] or "value" in names:
            self._notify_trait("value", self.value, self.value)

    observe.__doc__ = traitlets.HasTraits.observe.__doc__

    def destroy(self):
        self._destroyed = True
        if self.links is not None:
            self.links.clear()
        if self._timer_handle is not None:
            self._timer_handle.cancel()
            self._timer_handle = None
        parent = self.parent()
        traitlet = parent._traitlets[self.path]
        if traitlet is self:
            parent._traitlets.pop(self.path)


from .Cell import Cell
from ..core.structured_cell import StructuredCell
from ..core.cell import Cell as core_cell
from ..core.protocol.deserialize import deserialize_sync
from ..core.protocol.expression import get_subpath
from ..core.cache.buffer_cache import buffer_cache
import weakref

def set_fallback(cell, fallback_cell):
    try:
        core_cell = cell._get_cell()
    except Exception:
        return
    manager = core_cell._get_manager()

    fallback_core_cell = None
    if fallback_cell is not None:
        try:
            fallback_core_cell = fallback_cell._get_cell()
        except Exception:
            fallback_core_cell = None

    old_fallback = manager.get_fallback(core_cell)
    if old_fallback is not None and not old_fallback._destroyed:
        fallback_manager = old_fallback._get_manager()
        fallback_manager.remove_reverse_fallback(old_fallback, core_cell)

    if fallback_core_cell is None:
        manager.clear_fallback(core_cell)
    else:
        manager.set_fallback(core_cell, fallback_core_cell)
        fallback_manager = fallback_core_cell._get_manager()
        fallback_manager.add_reverse_fallback(fallback_core_cell, core_cell)
        checksum = fallback_core_cell.checksum
        if checksum is not None:
            fallback_manager.trigger_fallback(checksum, core_cell)


class Fallback:
    def __new__(cls, cell):
        if cell._fallback is not None:
            return cell._fallback
        self = super().__new__(cls)
        self.__init__(cell)
        return self

    def __init__(self, cell):
        if not isinstance(cell, Cell):
            raise TypeError(type(cell))
        self._cell = weakref.ref(cell)  # high-level cell!
        self._fallback_cell = None      # high-level cell!

    def __call__(self, fallback_cell):
        if fallback_cell is not None:
            if not isinstance(fallback_cell, Cell):
                raise TypeError(type(fallback_cell))
        cell = self._cell()
        if cell is None:
            return
        cell._fallback = self
        if fallback_cell is None:
            return self._clear()
        self._fallback_cell = weakref.ref(fallback_cell)
        ctx = cell._get_top_parent()
        fallback_ctx = fallback_cell._get_top_parent()
        if fallback_ctx is not ctx:
            fallback_ctx._reverse_fallbacks.add(self)
        set_fallback(cell, fallback_cell)

    def _clear(self):
        cell = self._cell()
        if cell is None:
            return
        cell._fallback = None
        set_fallback(cell, None)

    def _activate(self):
        """Activates the fallback.
        To be called after translation of the toplevel Context, of either cell or fallback_cell."""
        cell = self._cell()
        if cell is None:
            return
        if self._fallback_cell is None:
            return None        
        fb = self._fallback_cell()
        set_fallback(cell, fb)

    def __str__(self):
        cell = self._cell()
        if cell is None:
            return None
        if self._fallback_cell is None:
            return None        
        fb = self._fallback_cell()
        if fb is None:
            self._clear()
            return None
        result = "Fallback from {} to {}".format(cell, fb)
        return result

from .Cell import Cell
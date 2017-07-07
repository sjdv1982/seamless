import weakref

class Observer:
    """Observer class to observe cells from external Python code.

Whenever a cell changes value, the observer callback is notified.
Observers are never saved by ``context.tofile()``. Therefore, unlike macro
functions, observer callbacks can be arbitrary Python callables.

Parameters
----------

    cell: cell
      Seamless cell to observe
    callback: callable
      callback to be called whenever the cell changes.
      It must be a callable that takes one argument, the value of the cell
    """
    _callback = None
    def __init__(self, cell, callback):
        assert callable(callback)
        self._callback = callback
        self._set_cell(cell)

    def _set_cell(self, cell):
        from .cell import Cell
        assert isinstance(cell, Cell)
        self._cell = weakref.ref(cell)
        manager = cell._get_manager()
        manager.add_observer(cell, self._callback)

    def _remove_callback(self):
        if self._callback is not None:
            cell = self.cell
            manager = cell._get_manager()
            if cell is not None:
                manager.remove_observer(cell, self._callback)

    @property
    def cell(self):
        cell = self._cell
        if cell is None:
            return None
        else:
            return cell()
    @cell.setter
    def cell(self, cell):
        self._remove_callback()
        self._set_cell(cell)

    @property
    def callback(self):
        return self._callback
    @callback.setter
    def callback(self, callback):
        self._remove_callback()
        self._callback = callback
        if callback is not None:
            cell = self.cell
            if cell is not None:
                manager = cell._get_manager()
                manager.add_observer(cell, callback)

    def __del__(self):
        try:
            self._remove_callback()
        except:
            pass

observer = Observer

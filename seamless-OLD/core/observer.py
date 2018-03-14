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
    as_data: bool (default: False)
      If True, the callback is called with cell.data, rather than cell.value
    """
    _callback = None
    def __init__(self, cell, callback, as_data=False ):
        self.cell = cell
        assert callable(callback)
        self._callback = callback
        self._as_data = as_data
        self._update()

    def _update(self):
        self._remove_callback()
        callback = self._callback
        if callback is not None:
            cell = self.cell
            if cell is not None:
                manager = cell._get_manager()
                manager.add_observer(cell, callback, self._as_data)

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
        from .cell import Cell
        assert isinstance(cell, Cell)
        self._cell = weakref.ref(cell)
        self._update()

    @property
    def callback(self):
        return self._callback
    @callback.setter
    def callback(self, callback):
        self._callback = callback
        self._update()

    @property
    def as_data(self):
        return self._as_data
    @as_data.setter
    def as_data(self, as_data):
        self._as_data = as_data
        self._update()

    def __del__(self):
        try:
            self._remove_callback()
        except:
            pass

observer = Observer

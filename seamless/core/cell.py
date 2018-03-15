"""
modes and submodes that a *pin* can have, and that must be supported by a cell
These are specific for the low-level.
At the mid-level, the modes would be annotations/hints (i.e. not core),
 and the submodes would be cell languages: JSON, CSON, Silk, Python
"""
modes = ["copy", "ref", "signal"]
submodes = {
    "copy": ["json", "cson", "silk"],
    "ref": ["pythoncode"]
}

from . import SeamlessBase
from .macro import get_macro_mode
from copy import deepcopy
import hashlib

class CellBase(SeamlessBase):
    _exception = None
    _val = None
    _last_checksum = None
    def __init__(self, naming_pattern):
        assert get_macro_mode()
        super().__init__()
        ctx = get_active_context()
        if ctx is None:
            raise AssertionError("Cells can only be defined when there is an active context")
        ctx._add_new_cell(self, naming_pattern)

    @property
    def _value(self):
        return self._val

    @property.setter
    def _value(self, value):
        """Should only ever be set by the manager, since it bypasses validation, last checksum, status flags, etc."""
        self._value = value

    @property
    def value(self):
        return self._val

    def _check_mode(self, mode, submode=None):
        assert mode in modes, mode
        if submode is not None:
            assert submode in submodes[mode], (mode, submodes)

    def touch(self):
        """Forces a cell update, even though the value stays the same
        This triggers all workers that are connected to the cell"""
        manager = self._get_manager()
        manager.touch_cell(self)

    def set(self, value):
        """Update cell data from Python code in the main thread."""
        manager = self._get_manager()
        manager.set_cell(self, value)

    def serialize(self, mode, submode=None):
        self._check_mode(mode, submode)
        assert submode is None, submode
        assert self.status() == "OK", self.status()
        return self._serialize(mode, submode)

    def deserialize(self, value, mode, submode=None):
        """Should normally be invoked by the manager, since it does not notify the manager"""
        self._check_mode(mode, submode)
        assert submode is None, submode
        if value is None:
            self._val = None
            self._last_checksum = None
            self._status = self.StatusFlags.UNDEFINED
        self._validate(value)
        self._last_checksum = None
        self._deserialize(value, mode, submode)

    @property
    def exception(self):
        """The cell's current exception, as returned by sys.exc_info

        Returns None is there is no exception
        """
        return self._exception

    def _set_exception(self, exception):
        if exception is not None:
            self._status = self.StatusFlags.ERROR
            tb, exc, value = exception #to validate
        self._exception = exception

    def _validate(self, value):
        """Won't raise an exception, but may set .exception"""
        raise NotImplementedError

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

    def _checksum(self, value):
        raise NotImplementedError

    def checksum(self):
        assert self.status() == "OK"
        if self._last_checksum is not None:
            return self._last_checksum
        result = self._checksum(self._val)
        self._last_checksum = result
        return result

class Cell(CellBase):
    """Default class for cells.

Cells contain all the state in text form

Cells can be connected to inputpins, editpins, and other cells.
``cell.connect(pin)`` connects a cell to an inputpin or editpin

Output pins and edit pins can be connected to cells.
``pin.connect(cell)`` connects an outputpin or editpin to a cell

Use ``Cell.value`` to get its value.

Use ``Cell.status()`` to get its status.
"""

    def _checksum(self, value):
        return hashlib.md5(str(value).encode("utf-8")).hexdigest()

    def _validate(self, value):
        pass

    def _serialize(self, mode, submode=None):
        if mode == "copy":
            return deepcopy(self._val)
        else:
            return self._val

    def _deserialize(self, value, mode, submode=None):
        self._val = value

class PythonCell(Cell):
    """A cell containing Python code.
    """
    def _checksum(self, value):
        raise NotImplementedError

    def _validate(self, value):
        raise NotImplementedError

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError


class JsonCell(Cell):
    """A cell in JSON format (monolithic)"""

    def _checksum(self, value):
        raise NotImplementedError

    def _validate(self, value):
        raise NotImplementedError

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

class CsonCell(Cell):
    """A cell in CoffeeScript Object Notation (CSON) format
    When necessary, the contents of a CSON cell are automatically converted
    to JSON.
    """

    def _checksum(self, value):
        raise NotImplementedError

    def _validate(self, value):
        raise NotImplementedError

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

class Signal(Cell):
    """ A cell that does not contain any data
    When a signal is set, it is propagated as fast as possible:
      - If set from the main thread: immediately. Downstream workers are
         notified and activated (if synchronous) before set() returns
      - If set from another thread: as soon as run_work is called. Then,
         Downstream workers are notified and activated before any other
         non-signal notification.
    """

    def _checksum(self, value):
        return None

    def _validate(self, value):
        pass

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

def cell(*args, **kwargs):
    return Cell(*args, **kwargs)

print("TODO cell: struct cell, silk cell!")

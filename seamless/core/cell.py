"""
modes and submodes that a *pin* can have, and that must be supported by a cell
These are specific for the low-level.
At the mid-level, the modes would be annotations/hints (i.e. not core),
 and the submodes would be cell languages: JSON, CSON, Silk, Python
"""
modes = ["buffer", "copy", "ref", "signal"]
submodes = {
    "copy": ["json", "cson", "silk"],
    "ref": ["pythoncode", "json", "silk"]
}
celltypes = ("text", "python", "pytransformer", "json", "cson", "mixed")

from . import SeamlessBase
from .macro import get_macro_mode, macro_register
from ..mixed import io as mixed_io
from copy import deepcopy
import json
import hashlib

from ast import PyCF_ONLY_AST, FunctionDef
from .cached_compile import cached_compile

from .mount import MountItem
from ..silk import Silk
import numpy as np

transformer_patch = """
import inspect
def {0}():
    global __transformer_frame__
    __transformer_frame__ = inspect.currentframe()
"""

cell_counter = 0

class CellLikeBase(SeamlessBase):
    def __init__(self):
        global cell_counter
        assert get_macro_mode()
        super().__init__()
        cell_counter += 1
        self._counter = cell_counter
        macro_register.add(self)

    def __hash__(self):
        return self._counter


class CellBase(CellLikeBase):
    _exception = None
    _val = None
    _last_checksum = None
    _alternative_checksums = None #alternative checksums resulting from cosmetic updates
    _naming_pattern = "cell"
    _prelim_val = None
    _authoritative = True
    _overruled = False #a non-authoritative cell that has previously received a value
    _mount = None
    _mount_kwargs = None
    _mount_setter = None
    _slave = False   #Slave cells. Cannot be written to by API, do not accept connections,
                     #  and mounting is write-only unless there is a mount_setter.
                     # Slave cells are controlled by StructuredCell.
                     # TODO: make StructuredCell a bit less tyrannical, and allow slave
                     #  cells to be controlled by workers/macros external to the StructuredCell
                     # This will require a listener in the vein of mount_setter

    def status(self):
        """The cell's current status."""
        return self._status.name

    @property
    def authoritative(self):
        return self._authoritative

    @property
    def _value(self):
        return self._val

    @_value.setter
    def _value(self, value):
        """Should only ever be set by the manager, since it bypasses validation, last checksum, status flags, authority, etc."""
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
        return self

    def set(self, value):
        """Update cell data from Python code in the main thread."""
        assert not self._slave #slave cells are read-only
        if self._context is None:
            self._prelim_val = value, False #non-default-value prelim
        else:
            manager = self._get_manager()
            manager.set_cell(self, value)
        return self

    def set_default(self, value):
        """Provides a default value for the cell
        This value can be overwritten by workers"""
        if self._context is None:
            self._prelim_val = value, True #default-value prelim
        else:
            manager = self._get_manager()
            manager.set_cell(self, value, default=True)
        return self

    def set_from_buffer(self, value, checksum=None):
        """Sets a cell from a buffer value"""
        if self._context is None:
            self._prelim_val = value, False #non-default-value prelim
        else:
            manager = self._get_manager()
            manager.set_cell(self, value, from_buffer=True)
        return self

    def set_cosmetic(self, value):
        """Provides a cosmetic update to the cell
        that has no effect on its value"""
        if self._context is None:
            return
        if self._val is None:
            return
        manager = self._get_manager()
        manager.set_cell(self, value, cosmetic=True)
        return self

    def serialize(self, mode, submode=None):
        self._check_mode(mode, submode)
        assert self.status() == "OK", self.status()
        return self._serialize(mode, submode)

    def _reset_checksums(self):
        self._last_checksum = None
        self._alternative_checksums = None

    def _assign(self, value):
        assert value is not None
        v = self._val
        if not issubclass(type(value), type(v)):
            self._val = value
            return
        if isinstance(v, dict):
            v.clear()
            v.update(value)
        elif isinstance(v, list):
            v[:] = value #not for ndarray, since they must have the same shape
        else:
            self._val = value


    def deserialize(self, value, mode, submode=None, *, from_pin, default, cosmetic, force=False):
        """Should normally be invoked by the manager, since it does not notify the manager
        from_pin: can be True (normal pin that has authority), False (from code) or "edit" (edit pin)
        default: indicates a default value (pins may overwrite it)
        cosmetic: declares that the new value is equivalent to the old one (e.g. by adding a comment to a source code cell)
        force: force deserialization, even if slave (normally, force is invoked only by structured_cell)
        """
        assert from_pin in (True, False, "edit")
        if not force:
            assert not self._slave
        self._check_mode(mode, submode)
        old_status = self._status
        if value is None:
            different = (self._last_checksum is not None)
            self._val = None
            self._reset_checksums()
            self._status = self.StatusFlags.UNDEFINED
            return
        old_checksum = None
        if not cosmetic and value is not None:
            if old_status == self.StatusFlags.OK:
                old_checksum = self.checksum()
        self._validate(value)
        if cosmetic:
            cs = self._last_checksum
            if cs is not None:
                if self._alternative_checksums is None:
                    self._alternative_checksums = []
                self._alternative_checksums.append(cs)
        self._reset_checksums()
        self._deserialize(value, mode, submode)
        if from_pin == True:
            assert not self._authoritative
            self._un_overrule()
        elif from_pin == "edit":
            if not self._authoritative:
                self._overrule()
            else:
                self._un_overrule()
        elif from_pin == False:
            if not default and not self._authoritative:
                self._overrule()
        self._status = self.StatusFlags.OK
        if cosmetic:
            different = False
        elif old_checksum is None: #old checksum failed
            different = True
        elif value is not None:
            different = (self.checksum(may_fail=True) != old_checksum)
        else:
            pass #"different" has already been set
        return different

    def _overrule(self):
        if not self._overruled:
            print("Warning: overruling (setting value for non-authoritative cell) %s" % self.format_path())
            self._overruled = True

    def _un_overrule(self):
        if self._overruled:
            print("Warning: cell %s was formerly overruled, now updated by dependency" % self.format_path())
            self._overruled = False

    @property
    def exception(self):
        """The cell's current exception, as returned by sys.exc_info

        Returns None is there is no exception
        """
        return self._exception

    def _set_exception(self, exception):
        """Should normally be invoked by the manager, since it does not notify the manager"""
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

    def _checksum(self, value, *, buffer=False, may_fail=False):
        raise NotImplementedError

    def checksum(self, *, may_fail=False):
        if self.status() != "OK":
            return None
        assert self._val is not None
        if self._last_checksum is not None:
            return self._last_checksum
        result = self._checksum(self._val, may_fail=may_fail)
        self._last_checksum = result
        return result

    def connect(self, target):
        """connects to a target cell"""
        assert get_macro_mode() #or connection overlay mode, TODO
        manager = self._get_manager()
        manager.connect_cell(self, target)

    def as_text(self):
        raise NotImplementedError

    def mount(self, path, mode="rw", authority="cell"):
        """Performs a "lazy mount"; cell is mounted to the file when macro mode ends
        path: file path
        mode: "r", "w" or "rw"
        authority: "cell", "file" or "file-strict"
        """
        if self._mount_kwargs is None:
            raise NotImplementedError #cannot mount this type of cell
        kwargs = self._mount_kwargs
        self._mount = {
            "path": path,
            "mode": mode,
            "authority": authority
        }
        self._mount.update(self._mount_kwargs)
        MountItem(None, self,  **self._mount) #to validate parameters

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
    def _checksum(self, value, *, buffer=False, may_fail=False):
        return hashlib.md5(str(value).encode("utf-8")).hexdigest()

    def _validate(self, value):
        pass

    def _check_mode(self, mode, submode=None):
        super()._check_mode(mode, submode)
        assert (mode, submode) != ("ref", "pythoncode") #TODO

    def _serialize(self, mode, submode=None):
        if mode == "buffer":
            raise Exception("Cell '%s' cannot be serialized as buffer, use TextCell or JsonCell instead" % self.format_path())
        elif mode == "copy":
            assert submode is None, (mode, submode)
            return deepcopy(self._val)
        else:
            return self._val

    def _deserialize(self, value, mode, submode=None):
        if mode == "buffer":
            raise Exception("Cell '%s' cannot be de-serialized as buffer, use TextCell or JsonCell instead" % self.format_path())
        assert submode is None, (mode, submode)
        self._assign(value)

    def __str__(self):
        ret = "Seamless cell: " + self.format_path()
        return ret

    def as_text(self):
        if self._val is None:
            return None
        try:
            return str(self._val)
        except:
            return "<Cannot be rendered as text>"

class MixedCell(Cell):
    _mount_kwargs = {"binary": True}
    def __init__(self, storage_cell, form_cell):
        super().__init__()
        self.storage_cell = storage_cell
        self.form_cell = form_cell

    def _from_buffer(self, value):
        if value is None:
            return None
        storage = self.storage_cell.value
        form = self.form_cell.value
        return mixed_io.from_stream(value, storage, form)

    def _value_to_bytes(self, value, storage, form):
        if value is None:
            return None
        return mixed_io.to_stream(value, storage, form)

    def _to_bytes(self):
        storage = self.storage_cell.value
        form = self.form_cell.value
        return self._value_to_bytes(self._val, storage, form)

    def _checksum(self, value, *, buffer=False, may_fail=False):
        if buffer:
            b = value
        else:
            #assumes that storage and form are correct!
            storage = self.storage_cell.value
            form = self.form_cell.value
            if may_fail:
                try:
                    b = self._value_to_bytes(value, storage, form)
                except:
                    return None
            else:
                b = self._value_to_bytes(value, storage, form)
        return hashlib.md5(b).hexdigest()

    def _validate(self, value):
        return ###TODO: how to validate?? check that value conforms to form?

    def _serialize(self, mode, submode=None):
        if mode == "buffer":
            return self._to_bytes()
        elif mode == "copy":
            if submode == "silk":
                data = deepcopy(self._val)
                return Silk(data=data)
            elif submode == "cson":
                raise NotImplementedError
            else:
                return deepcopy(self._val)
        elif mode == "ref":
            assert submode in ("json", "silk", None)
            if submode == "silk":
                return Silk(data=self._val)
            else:
                return self._val
        else:
            return self._val

    def _deserialize(self, value, mode, submode=None):
        if mode == "buffer":
            self._assign(self._from_buffer(value))
        else:
            self._assign(value)

    def __str__(self):
        ret = "Seamless mixed cell: " + self.format_path()
        return ret




class TextCell(Cell):
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    def _serialize(self, mode, submode=None):
        if mode in ("buffer", "copy"):
            assert submode is None, (mode, submode)
            return deepcopy(self._val)
        else:
            return self._val

    def _deserialize(self, value, mode, submode=None):
        assert submode is None, (mode, submode)
        self._val = str(value)

    def as_text(self):
        if self._val is None:
            return None
        return str(self._val)

    def __str__(self):
        ret = "Seamless text cell: " + self.format_path()
        return ret


class PythonCell(Cell):
    """Python code object, used for reactors and macros"""
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    _naming_pattern = "pythoncell"

    _accept_shell_append = True

    #TODO: for serialization, store ._accept_shell_append
    # OR: make ._accept_shell_append editable as cell

    def _check_mode(self, mode, submode=None):
        CellBase._check_mode(self, mode, submode)

    def _shell_append(self, text):
        if not self._accept_shell_append:
            return
        if self._val is None:
            return
        new_value = self._val + "\n" + text
        self.set(new_value)

    def _validate(self, value):
        raise NotImplementedError #TODO

    def _serialize(self, mode, submode=None):
        if mode == "buffer":
            assert submode is None, (mode, submode)
            return deepcopy(self._val)
        assert mode == "ref" and submode == "pythoncode", (mode, submode)
        return self

    def _deserialize(self, value, mode, submode=None):
        if mode == "ref":
            self._val = value
            return
        assert mode in ("buffer", "copy"), mode
        assert submode is None, (mode, submode)
        self._val = str(value)

    def __str__(self):
        ret = "Seamless Python cell: " + self.format_path()
        return ret

class PyTransformerCell(PythonCell):
    """Python code object used for transformers (accepts one argument)"""

    def _validate(self, value):
        ast = cached_compile(value, "transformer", "exec", PyCF_ONLY_AST)
        is_function = (len(ast.body) == 1 and
                       isinstance(ast.body[0], FunctionDef))

        if is_function:
            self.func_name = ast.body[0].name
        else:
            self.func_name = "transform"

        self.is_function = is_function

class JsonCell(Cell):
    """A cell in JSON format (monolithic)"""
    #also provides copy+silk and ref+silk transport, but with an empty schema, and text form

    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    @staticmethod
    def _json(value):
        if value is None:
            return None
        return json.dumps(value, sort_keys=True, indent=2)

    def _to_json(self):
        return self._json(self.value)

    def _checksum(self, value, *, buffer=False, may_fail=False):
        if buffer:
            return super()._checksum(value)
        j = self._json(value)
        return super()._checksum(j)

    def _validate(self, value):
        #TODO: store validation errors
        json.dumps(value)

    def _serialize(self, mode, submode=None):
        if mode == "buffer":
            return self._to_json()
        elif mode == "copy":
            if submode == "silk":
                data = deepcopy(self._val)
                return Silk(data=data)
            elif submode == "cson":
                return self._to_json()
            else:
                return deepcopy(self._val)
        elif mode == "ref":
            assert submode in ("json", "silk", None)
            if submode == "silk":
                return Silk(data=self._val)
            else:
                return self._val
        else:
            return self._val

    def _from_buffer(self, value):
        return json.loads(value)

    def _deserialize(self, value, mode, submode=None):
        if mode == "buffer":
            self._assign(self._from_buffer(value))
        else:
            self._assign(value)

    def as_text(self):
        return self._to_json()

    def __str__(self):
        ret = "Seamless JSON cell: " + self.format_path()
        return ret


class CsonCell(Cell):
    """A cell in CoffeeScript Object Notation (CSON) format
    When necessary, the contents of a CSON cell are automatically converted
    to JSON.
    """

    def _checksum(self, value, *, buffer=False, may_fail=False):
        raise NotImplementedError

    def _validate(self, value):
        raise NotImplementedError

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

    def __str__(self):
        ret = "Seamless CSON cell: " + self.format_path()
        return ret

class Signal(Cell):
    """ A cell that does not contain any data
    When a signal is set, it is propagated as fast as possible:
      - If set from the main thread: immediately. Downstream workers are
         notified and activated (if synchronous) before set() returns
      - If set from another thread: as soon as run_work is called. Then,
         Downstream workers are notified and activated before any other
         non-signal notification.
    """
    _naming_pattern = "signal"

    def _checksum(self, value, *, buffer=False, may_fail=False):
        return None

    def _validate(self, value):
        pass

    def _serialize(self, mode, submode=None):
        raise NotImplementedError

    def _deserialize(self, value, mode, submode=None):
        raise NotImplementedError

    def __str__(self):
        ret = "Seamless signal: " + self.format_path()
        return ret

def cell(celltype=None, **kwargs):
    if celltype == "text":
        return TextCell()
    elif celltype == "python":
        return PythonCell(**kwargs)
    elif celltype == "pytransformer":
        return PyTransformerCell(**kwargs)
    elif celltype == "json":
        return JsonCell(**kwargs)
    elif celltype == "cson":
        return CsonCell(**kwargs)
    elif celltype == "mixed":
        return MixedCell(**kwargs)
    else:
        return Cell(**kwargs)

def textcell():
    return TextCell()

def pythoncell():
    return PythonCell()

def pytransformercell():
    return PyTransformerCell()

extensions = {
    TextCell: ".txt",
    JsonCell: ".json",
    CsonCell: ".cson",
    PythonCell: ".py",
    MixedCell: ".mixed",
}
from ..mixed import MAGIC_SEAMLESS

print("TODO cell: CSON cell")
print("TODO cell: PyImport cell") #cell that does imports, executed already upon code definition; code injection causes an exec()
#...and TODO: cache cell, evaluation cell, event stream

#TODO: a serialization protocol to establish data transfer over a cell-to-cell (alias) connection
# it depends on three variables:
# - the alias mode (argument to manager.connect_cell)
# - the type / some attribute of the source cell
# - the type / some attribute of the target cell

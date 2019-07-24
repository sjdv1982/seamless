import inspect
from weakref import WeakSet

from . import SeamlessBase
from .macro_mode import get_macro_mode
from .utils import strip_source
from copy import deepcopy

cell_counter = 0

class Cell(SeamlessBase):
    """Default class for cells.
    
Cells can be connected to inputpins, editpins, and other cells.
``cell.connect(pin)`` connects a cell to an inputpin or editpin

Output pins and edit pins can be connected to cells.
``pin.connect(cell)`` connects an outputpin or editpin to a cell

Use ``Cell.value`` to get its value.

Use ``Cell.status()`` to get its status.
"""
    _celltype = None
    _subcelltype = None
    _checksum = None
    _void = True
    _prelim_val = None
    _prelim_checksum = None
    _unmounted = False

    _mount = None
    _mount_kwargs = None
    _mount_setter = None
    _lib_path = None # Set by library.libcell
    _paths = None #WeakSet of Path object weakrefs
    """
      Sovereignty
      A low level cell may be sovereign if it has a 1:1 correspondence to a mid-level element.
      Sovereign cells are authoritative, they may be changed, and changes to sovereign cells do not cause
      the translation macro to re-trigger.
      When a translation macro is re-triggered for another reason (or when the mid-level is serialized),
      the mid-level element is dynamically read from the sovereign cell (no double representation)
    """
    _sovereign = False
    _observer = None
    _traitlets = None
    _share_callback = None
    _monitor = None # Only changed for MixedCells that are data or buffer of a structuredcell

    def __init__(self):
        global cell_counter
        super().__init__()
        cell_counter += 1
        self._counter = cell_counter
        self._paths = WeakSet()
        self._traitlets = []

    def _set_context(self, ctx, name):
        assert self._checksum is None
        super()._set_context(ctx, name)
        assert self._context() is ctx
        manager = self._get_manager()
        manager.register_cell(self)
        if self._prelim_val is not None:
            value, from_buffer = self._prelim_val
            if from_buffer:
                self.set_buffer(value)
            else:
                self.set(value)
            self._prelim_val = None
        elif self._prelim_checksum is not None:
            checksum, initial, is_buffercell = self._prelim_checksum
            self._set_checksum(self, checksum, initial, is_buffercell)
            self._prelim_checksum = None

    def __hash__(self):
        return self._counter

    def __str__(self):
        ret = "Seamless %s: " % type(self).__name__ + self._format_path()
        return ret

    @property
    def status(self):
        """The cell's current status."""
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        status = self._get_manager().status[self]
        keys = set(status.keys())
        if keys == set([None]):
            return status[None]
        elif keys == set([None, ()]):
            return status[()]
        else:
            result = {}
            for k,v in status.items():
                result[k] = str(v) 
            return result

    @property
    def checksum(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        checksum = manager.get_cell_checksum(self)
        if checksum is None:
            return None
        return checksum.hex()

    @property
    def void(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        void = manager.get_cell_void(self)
        return void

    @property
    def semantic_checksum(self):        
        raise NotImplementedError # livegraph branch
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        checksum = manager.get_cell_checksum(self)
        raise NotImplementedError # livegraph branch
        #return checksum.hex()

    @property
    def authoritative(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        raise NotImplementedError # livegraph branch

    @property
    def buffer(self):
        """Return the cell's buffer.        
        The cell's checksum is the SHA3-256 hash of this."""
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            if self._lib_path is not None:
                from .library import lib_get_buffer
                return lib_get_buffer(self._prelim_checksum, self)                
            else:
                raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        return manager.get_cell_buffer(self)

    def _get_value(self, copy):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            if self._lib_path is not None:
                from .library import lib_get_value
                return lib_get_value(self._prelim_checksum, self)                
            else:
                raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        return manager.get_cell_value(self, copy=copy)

    @property
    def value(self):
        """Returns a copy of the cell's value
        cell.set(cell.value) is guaranteed to be a no-op"""
        return self._get_value(copy=True)

    @property
    def data(self):
        """Returns the cell's value, without making a copy
        cell.set(cell.data) is guaranteed to be a no-op"""
        return self._get_value(copy=False)

    def set(self, value):
        """Update cell data from the terminal."""
        if self._context is None:
            self._prelim_checksum = None
            self._prelim_val = value, False
        else:
            manager = self._get_manager()
            manager.set_cell(
              self, value
            )
        return self

    def set_buffer(self, buffer):
        """Update cell buffer from the terminal."""
        if self._context is None:
            self._prelim_checksum = None
            self._prelim_val = buffer, True
        else:
            manager = self._get_manager()
            manager.set_buffer(
              self, buffer
            )
        return self

    def _set_checksum(self, checksum, initial=False, is_buffercell=False):
        """Specifies the checksum of the data (hex format)        
        
        If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph).
        Else, cell cannot be the .data or .buffer attribute of a StructuredCell, and cannot have any incoming connection.
        
        However, if "is_buffercell" is True, then the cell can be a .buffer attribute of a StructuredCell
        """        
        if self._context is None:
            self._prelim_val = None
            self._prelim_checksum = checksum, initial, is_buffercell
        else:
            manager = self._get_manager()
            manager.set_cell_checksum(
              self, bytes.fromhex(checksum), initial, is_buffercell
            )
        return self

    def set_checksum(self, checksum):
        """Specifies the checksum of the data (hex format)"""
        self._set_checksum(checksum)
        return self

    def set_label(self, label):
        """Labels the current value of the cell
        Until redefined, this label will continue to point to this value, 
        even after the cell has changed"""
        return self._get_manager().set_cell_label(self, label)

    def from_label(self, label):
        if get_macro_mode():
            raise Exception("To guarantee macro determinism, this must not be run in macro mode")
        return self._get_manager().set_cell_from_label(self, label, subpath=None)

    @property
    def label(self):
        return self._get_manager().get_cell_label(self)

    def from_buffer(self, value):
        """Sets a cell from a buffer value"""
        return self._set(value, True)

    def from_file(self, filepath):
        ok = False
        if self._mount_kwargs is not None:
            if "binary" in self._mount_kwargs:
                binary = self._mount_kwargs["binary"]
                if not binary:
                    if "encoding" in self._mount_kwargs:
                        encoding = self._mount_kwargs["encoding"]
                        ok = True
                else:
                    ok = True
        if not ok:
            raise TypeError("Cell %s cannot be loaded from file" % self)
        filemode = "rb" if binary else "r"
        with open(filepath, filemode, encoding=encoding) as f:
            filevalue = f.read()
        return self.from_buffer(filevalue)

    def connect(self, target):
        """connects the cell to a target"""
        manager = self._get_manager()
        target_subpath = None
        if isinstance(target, Inchannel):
            target_subpath = target.path
            target = target.structured_cell().buffer
        elif isinstance(target, Editchannel):
            raise TypeError("Editchannels cannot be connected to cells, only to workers")
        elif isinstance(target, Outchannel):
            raise TypeError("Outchannels must be the source of a connection, not the target")
        
        if not isinstance(target, Cell):
            raise TypeError(target)
        manager.connect(self, None, target, target_subpath)
        return self

    def as_text(self):
        raise NotImplementedError

    def set_file_extension(self, extension):
        if self._mount is None:
            self._mount = {}
        self._mount.update({"extension": extension})

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        """Performs a "lazy mount"; cell is mounted to the file when macro mode ends
        path: file path (can be None if an ancestor context has been mounted)
        mode: "r", "w" or "rw"
        authority: "cell", "file" or "file-strict"
        persistent: whether or not the file persists after the context has been destroyed
        """
        from .context import Context
        assert is_dummy_mount(self._mount) #Only the mountmanager may modify this further!
        if self._mount_kwargs is None:
            raise NotImplementedError #cannot mount this type of cell
        if self._context is not None and isinstance(self._context(), Context):
            msg = "Mounting is not possible after a cell has been bound to a context"
            raise Exception(msg)

        kwargs = self._mount_kwargs
        if self._mount is None:
            self._mount = {}
        self._mount.update({
            "autopath": False,
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent,
        })
        self._mount.update(self._mount_kwargs)
        MountItem(None, self, dummy=True, **self._mount) #to validate parameters        
        return self

    def _add_traitlet(self, traitlet, trigger=True):
        from ..highlevel.SeamlessTraitlet import SeamlessTraitlet
        assert isinstance(traitlet, SeamlessTraitlet)
        self._traitlets.append(traitlet)
        if trigger and self.checksum is not None:
            traitlet.receive_update(self.checksum)


    def _set_observer(self, observer, trigger=True):
        self._observer = observer
        if trigger and self.checksum is not None:
            observer(self.checksum)

    def _set_share_callback(self, share_callback):
        self._share_callback = share_callback

    def destroy(self, *, from_del=False):
        super().destroy(from_del=from_del)
        if not from_del:
            self._get_manager()._destroy_cell(self)
            for path in list(self._paths):
                path._bind(None, trigger=True)
        self._unmount()
        
    def _unmount(self, from_del=False):
        from .macro import Macro
        if self._unmounted:
            return
        self._unmounted = True
        manager = self._root()._get_manager()
        mountmanager = manager.mountmanager
        if not is_dummy_mount(self._mount):
            mountmanager.unmount(self, from_del=from_del)

class ArrayCell(Cell):
    """A cell in binary array (Numpy) format"""
    
    _mount_kwargs = {"binary": True}
    _celltype = "array"

    def __str__(self):
        ret = "Seamless array cell: " + self._format_path()
        return ret

class MixedCell(Cell):
    _mount_kwargs = {"binary": True}
    _celltype = "mixed"
    _silk = None

    def set(self, value):
        #storage, form = get_form(value)
        #v = (storage, form, value)
        return self._set(value, False)

    @property
    def value(self):
        raise NotImplementedError # livegraph branch
        v = super().value
        if v is None:
            return None        
        if not isinstance(v, tuple): return v ### KLUDGE, shouldn't happen
        return v[2]

    @property
    def storage(self):
        raise NotImplementedError # livegraph branch
        from ..mixed.get_form import get_form
        v = super().value
        if v is None:
            return None        
        if not isinstance(v, tuple): return get_form(v)[0] ### KLUDGE, shouldn't happen
        return v[0]
    
    @property
    def form(self):
        raise NotImplementedError # livegraph branch
        from ..mixed.get_form import get_form
        v = super().value
        if v is None:
            return None        
        if not isinstance(v, tuple): return get_form(v)[1] ### KLUDGE, shouldn't happen
        return v[1]


    def __str__(self):
        ret = "Seamless mixed cell: " + self._format_path()
        return ret


class TextCell(Cell):
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    _celltype = "text"

    def __str__(self):
        ret = "Seamless text cell: " + self._format_path()
        return ret

class PythonCell(Cell):
    """Generic Python code object"""
    _celltype = "python"
    _subcelltype = None
    _mount_kwargs = {"encoding": "utf-8", "binary": False}


    def set(self, value):
        """Update cell data from the command line.
        Python function objects are converted to source code"""
        if inspect.isfunction(value):
            code = inspect.getsource(value)
            code = strip_source(code)
            value = code
        return self._set(value, False)

    def __str__(self):
        ret = "Seamless Python cell: " + self._format_path()
        return ret

class PyReactorCell(PythonCell):
    """Python code object used for reactors
    a "PINS" object will be inserted into its namespace"""
    _subcelltype = "reactor"


class PyTransformerCell(PythonCell):
    """Python code object used for transformers
    Each input will be an argument"""
    _subcelltype = "transformer"



class PyMacroCell(PythonCell):
    """Python code object used for macros
    The context "ctx" will be the first argument.
    Each input will be an argument
    If the macro is a function, ctx must be returned
    """
    _subcelltype = "macro"

class IPythonCell(Cell):
    _celltype = "ipython"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless IPython cell: " + self._format_path()
        return ret


class PlainCell(Cell):
    """A cell in plain (i.e. JSON-serializable) format"""
    _celltype = "plain"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    _monitor = None
    _silk = None

    def __str__(self):
        ret = "Seamless plain cell: " + self._format_path()
        return ret


class CsonCell(Cell):
    """A cell in CoffeeScript Object Notation (CSON) format
    When necessary, the contents of a CSON cell are automatically converted
    to plain.
    """
    _celltype = "cson"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless CSON cell: " + self._format_path()
        return ret


celltypes = {
    "text": TextCell,
    "python": PythonCell,
    "ipython": IPythonCell,
    "transformer": PyTransformerCell,
    "reactor": PyReactorCell,
    "macro": PyMacroCell,
    "plain": PlainCell,
    "cson": CsonCell,
    "array": ArrayCell,
    "mixed": MixedCell
}

def cell(celltype="plain", **kwargs):
    cellclass = celltypes[celltype]
    return cellclass(**kwargs)

def textcell():
    return TextCell()

def pythoncell():
    return PythonCell()

def pytransformercell():
    return PyTransformerCell()

def pyreactorcell():
    return PyReactorCell()

def pymacrocell():
    return PyMacroCell()

def ipythoncell():
    return IPythonCell()

def plaincell():
    return PlainCell()

def csoncell():
    return CsonCell()

def arraycell():
    return ArrayCell()

def mixedcell():
    return MixedCell()


extensions = {
    TextCell: ".txt",
    PlainCell: ".json",
    CsonCell: ".cson",
    PythonCell: ".py",
    IPythonCell: ".ipy",
    PyTransformerCell: ".py",
    PyReactorCell: ".py",
    PyMacroCell: ".py",
    IPythonCell: ".ipy",
    MixedCell: ".mixed",
    ArrayCell: ".npy",
}
_cellclasses = [cellclass for cellclass in globals().values() if isinstance(cellclass, type) \
  and issubclass(cellclass, Cell)]
celltypes = {cellclass._celltype:cellclass for cellclass in _cellclasses}
subcelltypes = {cellclass._subcelltype:cellclass for cellclass in _cellclasses if cellclass._subcelltype is not None}

from .unbound_context import UnboundManager
from .mount import MountItem
from .mount import is_dummy_mount
from ..mixed.get_form import get_form
from .structured_cell import Inchannel, Outchannel, Editchannel

"""
TODO Documentation: only-text changes
     adding comments / breaking up lines to a Python cell will affect a syntax highlighter, but not a transformer, it is only text
     (a refactor that changes variable names would still trigger transformer re-execution, but this is probably the correct thing to do anyway)
     Same for CSON cells: if the CSON is changed but the corresponding JSON stays the same, the checksum stays the same.
     But the text checksum changes, and a text cell or text inputpin will receive an update.
"""


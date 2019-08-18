import inspect
from weakref import WeakSet

from . import SeamlessBase
from copy import deepcopy
from .status import StatusReasonEnum

cell_counter = 0

text_types = (
    "text", "python", "ipython", "cson", "yaml",
    "str", "int", "float", "bool",
)

text_types2 = (
    "text", "python", "ipython", "cson", "yaml",
)

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
    _status_reason = StatusReasonEnum.UNDEFINED
    _prelim_val = None
    _prelim_checksum = None
    _unmounted = False

    _mount = None
    _mount_kwargs = None
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

    _canceling = False

    def __init__(self):
        global cell_counter
        super().__init__()
        cell_counter += 1
        self._counter = cell_counter
        self._paths = WeakSet()
        self._traitlets = []

    def _set_context(self, ctx, name):
        assert self._checksum is None
        has_ctx = self._context is not None
        super()._set_context(ctx, name)
        assert self._context() is ctx
        manager = self._get_manager()
        if not has_ctx:
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
            self._set_checksum(checksum.hex(), initial, is_buffercell)
            self._prelim_checksum = None

    def __hash__(self):
        return self._counter

    def __str__(self):
        ret = "Seamless %s cell: " % self._celltype + self._format_path()
        return ret

    def _get_status(self):
        from .status import status_cell, format_status      
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")        
        status = status_cell(self)
        return status

    @property
    def status(self):        
        """The cell's current status."""        
        from .status import format_status
        if self._monitor is not None:
            raise NotImplementedError # livegraph branch
        status = self._get_status()
        statustxt = format_status(status)
        return "Status: " + statustxt 

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
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        checksum = bytes.fromhex(self.checksum)
        transformation_cache = manager.cachemanager.transformation_cache
        sem_checksum = transformation_cache.syntactic_to_semantic(
            checksum,
            self._celltype,
            self._subcelltype,
            manager.buffer_cache
        )
        return sem_checksum.hex()

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
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        buffer, _ = manager.get_cell_buffer_and_checksum(self)
        return buffer

    @property
    def buffer_and_checksum(self):
        """Return the cell's buffer and checksum."""
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception("Cannot ask the cell value of a context that is being constructed by a macro")
        buffer, checksum = manager.get_cell_buffer_and_checksum(self)
        return buffer, checksum

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

    def set_buffer(self, buffer, checksum=None):
        """Update cell buffer from the terminal.
        If the checksum is known, it can be provided as well."""
        assert buffer is None or isinstance(buffer, bytes)
        if self._context is None:
            self._prelim_checksum = None
            self._prelim_val = buffer, True
        else:
            manager = self._get_manager()
            manager.set_cell_buffer(
              self, buffer, checksum
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
            if checksum is not None:
                checksum = bytes.fromhex(checksum)
            self._prelim_checksum = checksum, initial, is_buffercell
        else:
            manager = self._get_manager()
            if checksum is not None:
                checksum = bytes.fromhex(checksum)
            manager.set_cell_checksum(
              self, checksum, initial, is_buffercell
            )
        return self

    def set_checksum(self, checksum):
        """Specifies the checksum of the data (hex format)"""
        self._set_checksum(checksum)
        return self

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
        if not binary:
            filevalue = filevalue.encode()
        return self.set_buffer(filevalue)

    def connect(self, target):
        """connects the cell to a target"""
        from .worker import InputPin, EditPin, OutputPin
        from .transformer import Transformer
        from .macro import Macro, Path
        from .link import Link
        manager = self._get_manager()
        target_subpath = None

        if isinstance(target, Link):
            target = target.get_linked()

        if isinstance(target, Inchannel):
            target_subpath = target.path
            target = target.structured_cell().buffer
        elif isinstance(target, Outchannel):
            raise TypeError("Outchannels must be the source of a connection, not the target")
        
        if isinstance(target, Cell):
            assert not target._monitor
        elif isinstance(target, Path):
            pass
        elif isinstance(target, InputPin):
            pass
        elif isinstance(target, EditPin):
            pass
        elif isinstance(target, OutputPin):
            raise TypeError("Output pins must be the source of a connection, not the target")
        elif isinstance(target, Transformer):
            raise TypeError("Transformers cannot be connected directly, select a pin")
        elif isinstance(target, Reactor):
            raise TypeError("Reactors cannot be connected directly, select a pin")
        elif isinstance(target, Macro):
            raise TypeError("Reactors cannot be connected directly, select a pin")
        else:
            raise TypeError(type(target))
        manager.connect(self, None, target, target_subpath)
        return self

    def has_authority(self, path=None):
        manager = self._get_manager()
        return manager.livegraph.has_authority(self, path)

    def set_file_extension(self, extension):
        if self._mount is None:
            self._mount = {}
        self._mount.update({"extension": extension})
        return self

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
        if self._destroyed:            
            return 
        super().destroy(from_del=from_del)
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

class BinaryCell(Cell):
    """A cell in binary (Numpy) format"""
    
    _mount_kwargs = {"binary": True}
    _celltype = "binary"


class MixedCell(Cell):
    _mount_kwargs = {"binary": True}
    _celltype = "mixed"

    @property
    def storage(self):
        from ..mixed.get_form import get_form
        v = super().value
        if v is None:
            return None        
        return get_form(v)[0]
    
    @property
    def form(self):
        from ..mixed.get_form import get_form
        v = super().value
        if v is None:
            return None
        return get_form(v)[1]  



class TextCell(Cell):
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    _celltype = "text"

class PythonCell(Cell):
    """Generic Python code object
    Buffer ends with a newline"""
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
        return super().set(value)

    def __str__(self):
        ret = "Seamless Python cell: " + self._format_path()
        return ret

class PyReactorCell(PythonCell):
    """Python code object used for reactors
    a "PINS" object will be inserted into its namespace
    Buffer ends with a newline"""
    _subcelltype = "reactor"

    def __str__(self):
        ret = "Seamless Python reactor code cell: " + self._format_path()
        return ret


class PyTransformerCell(PythonCell):
    """Python code object used for transformers
    Each input will be an argument
    Buffer ends with a newline"""
    _subcelltype = "transformer"

    def __str__(self):
        ret = "Seamless Python transformer code cell: " + self._format_path()
        return ret



class PyMacroCell(PythonCell):
    """Python code object used for macros
    The context "ctx" will be the first argument.
    Each input will be an argument
    If the macro is a function, ctx must be returned
    Buffer ends with a newline
    """
    _subcelltype = "macro"

    def __str__(self):
        ret = "Seamless Python macro code cell: " + self._format_path()
        return ret

class IPythonCell(Cell):
    """A cell in IPython format (e.g. a Jupyter cell). Buffer ends with a newline"""
    _celltype = "ipython"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless IPython cell: " + self._format_path()
        return ret


class PlainCell(TextCell):
    """A cell in plain (i.e. JSON-serializable) format. Buffer ends with a newline"""
    _celltype = "plain"


class CsonCell(TextCell):
    """A cell in CoffeeScript Object Notation (CSON) format. Buffer ends with a newline"""
    _celltype = "cson"

class YamlCell(TextCell):
    """A cell in YAML format. Buffer ends with a newline"""
    _celltype = "yaml"

class StrCell(TextCell):
    """A cell containing a string, wrapped in double quotes. Buffer ends with a newline"""
    _celltype = "str"

class BytesCell(TextCell):
    """A cell containing bytes"""
    _celltype = "bytes"

class IntCell(TextCell):
    """A cell containing an integer. Buffer ends with a newline"""
    _celltype = "int"

class FloatCell(TextCell):
    """A cell containing a float. Buffer ends with a newline"""
    _celltype = "float"

class BoolCell(TextCell):
    """A cell containing a bool. Buffer ends with a newline"""
    _celltype = "bool"

cellclasses = {
    "text": TextCell,
    "python": PythonCell,
    "ipython": IPythonCell,
    "transformer": PyTransformerCell,
    "reactor": PyReactorCell,
    "macro": PyMacroCell,
    "plain": PlainCell,
    "cson": CsonCell,
    "binary": BinaryCell,
    "mixed": MixedCell,
    "yaml": YamlCell,
    "str": StrCell,
    "bytes": BytesCell,
    "int": IntCell,
    "float": FloatCell,
    "bool": BoolCell,
}

def cell(celltype="plain", **kwargs):
    if celltype is None:
        celltype = "plain"
    cellclass = cellclasses[celltype]
    return cellclass(**kwargs)

_cellclasses = [cellclass for cellclass in globals().values() if isinstance(cellclass, type) \
  and issubclass(cellclass, Cell)]

extensions = {cellclass: ".txt" for cellclass in _cellclasses}
extensions.update({
    TextCell: ".txt",
    PlainCell: ".json",
    CsonCell: ".cson",
    YamlCell: ".yaml",
    BytesCell: ".dat",
    PythonCell: ".py",
    PyTransformerCell: ".py",
    PyReactorCell: ".py",
    PyMacroCell: ".py",
    IPythonCell: ".ipy",
    MixedCell: ".mixed",
    BinaryCell: ".npy",
})

celltypes = {cellclass._celltype:cellclass for cellclass in _cellclasses if cellclass._celltype is not None}
subcelltypes = {cellclass._subcelltype:cellclass for cellclass in _cellclasses if cellclass._subcelltype is not None}
subcelltypes["module"] = None

from .unbound_context import UnboundManager
from .mount import MountItem
from .mount import is_dummy_mount
from ..mixed.get_form import get_form
from .structured_cell import Inchannel, Outchannel
from .macro_mode import get_macro_mode
from .utils import strip_source

"""
TODO Documentation: only-text changes
     adding comments / breaking up lines to a Python cell will affect a syntax highlighter, but not a transformer, it is only text
     (a refactor that changes variable names would still trigger transformer re-execution, but this is probably the correct thing to do anyway)
     Same for CSON cells: if the CSON is changed but the corresponding JSON stays the same, the checksum stays the same.
     But the text checksum changes, and a text cell or text inputpin will receive an update.
"""


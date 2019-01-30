from . import SeamlessBase
from .macro_mode import with_macro_mode
from . import macro_register, get_macro_mode

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
    _storage_type = None
    _default_access_mode = None
    _content_type = None
    _prelim_val = None

    _mount = None
    _mount_kwargs = None
    _mount_setter = None
    _lib_path = None # Set by library.libcell
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
    _share_callback = None

    def __init__(self):
        global cell_counter
        super().__init__()
        cell_counter += 1
        self._counter = cell_counter
        if get_macro_mode():
            macro_register.add(self)

    def _set_context(self, ctx, name):
        super()._set_context(ctx, name)
        self._get_manager().register_cell(self)
        if self._prelim_val is not None:
            value, from_buffer = self._prelim_val
            self._get_manager().set_cell(self, value, from_buffer=from_buffer)
            self._prelim_val = None

    def __hash__(self):
        return self._counter

    def __str__(self):
        ret = "Seamless %s: " % type(self).__name__ + self._format_path()
        return ret

    @property
    def status(self):
        """The cell's current status."""
        return self._get_manager().status[self]

    @property
    def checksum(self):
        manager = self._get_manager()
        checksum = manager.cell_cache.cell_to_buffer_checksums.get(self)
        if checksum is None:
            return None
        return checksum.hex()

    @property
    def semantic_checksum(self):        
        manager = self._get_manager()
        checksum = manager.cell_cache.cell_to_buffer_checksums.get(self)        
        if checksum is None:
            return None
        default_accessor = manager.get_default_accessor(self)
        default_expression = default_accessor.to_expression(checksum)
        semantic_key = manager.expression_cache.expression_to_semantic_key.get(default_expression.get_hash())
        if semantic_key is None:
            print("cache miss")
            buffer_item = manager.value_cache.get_buffer(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = manager.cache_expression(default_expression, buffer)
        semantic_checksum, _, _, _ = semantic_key
        return semantic_checksum.hex()

    @property
    def authoritative(self):
        manager = self._get_manager()
        return manager.cell_cache.cell_to_authority[self]


    @property
    def value(self):
        """Returns the value of the cell
        Usually, this is the same as the data"""
        manager = self._get_manager()
        checksum = manager.cell_cache.cell_to_buffer_checksums.get(self)        
        if checksum is None:
            return None
        default_accessor = manager.get_default_accessor(self)
        default_expression = default_accessor.to_expression(checksum)
        value = manager.get_expression(default_expression)
        return value

    @property
    def data(self):
        """Returns the cell's data
        cell.set(cell.data) is guaranteed to be a no-op"""
        raise NotImplementedError ###cache branch

    def touch(self):
        """Forces a cell update, even though the value stays the same
        This triggers all workers that are connected to the cell"""
        manager = self._get_manager()
        manager.touch_cell(self)
        return self

    def _set(self, value, from_buffer):
        if self._context is None:
            self._prelim_val = value, False
        else:
            manager = self._get_manager()
            manager.set_cell(self, value, from_buffer=from_buffer)
        return self

    def set(self, value):
        """Update cell data from the terminal."""
        return self._set(value, False)

    def set_checksum(self, checksum):
        """Specifies the checksum of the data (hex format)"""
        return self._get_manager().set_cell_checksum(self, bytes.fromhex(checksum))

    def set_label(self, label):
        """Labels the current value of the cell
        Until redefined, this label will continue to point to this value, 
        even after the cell has changed"""
        return self._get_manager().set_cell_label(self, label)

    def from_label(self, label):
        return self._get_manager().set_cell_from_label(self, label)

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

    @with_macro_mode
    def connect(self, target):
        """connects to a target cell"""
        manager = self._get_manager()
        manager.connect_cell(self, target)
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
        from .mount import is_dummy_mount
        assert is_dummy_mount(self._mount) #Only the mountmanager may modify this further!
        if self._root()._direct_mode:
            raise Exception("Root context must have been constructed in macro mode")
        if self._mount_kwargs is None:
            raise NotImplementedError #cannot mount this type of cell
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

    def _set_observer(self, observer):
        self._observer = observer
        if self._val is not None:
            observer(self._val)

    def _set_share_callback(self, share_callback):
        self._share_callback = share_callback


class ArrayCell(Cell):
    """A cell in binary array (Numpy) format"""
    
    _mount_kwargs = {"binary": True}
    _celltype = "array"
    _storage_type = "binary"
    _default_access_mode = "binary"
    _content_type = "binary"

    def __str__(self):
        ret = "Seamless array cell: " + self._format_path()
        return ret

class MixedCell(Cell):
    _mount_kwargs = {"binary": True}
    _celltype = "mixed"
    _storage_type = "mixed"
    _default_access_mode = "mixed"
    _content_type = "mixed"

    def __str__(self):
        ret = "Seamless mixed cell: " + self._format_path()
        return ret


class TextCell(Cell):
    _mount_kwargs = {"encoding": "utf-8", "binary": False}
    _celltype = "text"
    _storage_type = "text"
    _default_access_mode = "text"
    _content_type = "text"

    def __str__(self):
        ret = "Seamless text cell: " + self._format_path()
        return ret

class PythonCell(Cell):
    """Generic Python code object"""
    _celltype = "python"
    _subcelltype = None
    _storage_type = "text"
    _default_access_mode = "pythoncode"
    _content_type = "python"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless Python cell: " + self._format_path()
        return ret

class PyReactorCell(PythonCell):
    """Python code object used for reactors
    a "PINS" object will be inserted into its namespace"""
    _subcelltype = "reactor"
    _content_type = "reactor"


class PyTransformerCell(PythonCell):
    """Python code object used for transformers
    Each input will be an argument"""
    _subcelltype = "transformer"
    _content_type = "transformer"


class PyMacroCell(PythonCell):
    """Python code object used for macros
    The context "ctx" will be the first argument.
    Each input will be an argument
    If the macro is a function, ctx must be returned
    """
    _subcelltype = "macro"
    _content_type = "macro"


class IPythonCell(Cell):
    _celltype = "ipython"
    _storage_type = "text"
    _default_access_mode = "text"
    _content_type = "ipython"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless IPython cell: " + self._format_path()
        return ret


class PlainCell(Cell):
    """A cell in plain (i.e. JSON-serializable) format"""
    _celltype = "plain"
    _storage_type = "text"
    _default_access_mode = "plain"
    _content_type = "plain"
    _mount_kwargs = {"encoding": "utf-8", "binary": False}

    def __str__(self):
        ret = "Seamless plain cell: " + self._format_path()
        return ret


class CsonCell(Cell):
    """A cell in CoffeeScript Object Notation (CSON) format
    When necessary, the contents of a CSON cell are automatically converted
    to plain.
    """
    _celltype = "cson"
    _storage_type = "text"
    _default_access_mode = "plain"
    _content_type = "cson"
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

"""
TODO Documentation: only-text changes
     adding comments / breaking up lines to a Python cell will affect a syntax highlighter, but not a transformer, it is only text
     (a refactor that changes variable names would still trigger transformer re-execution, but this is probably the correct thing to do anyway)
     Same for CSON cells: if the CSON is changed but the corresponding JSON stays the same, the checksum stays the same.
     But the text checksum changes, and a text cell or text inputpin will receive an update.
"""

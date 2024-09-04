import inspect
import textwrap
from weakref import WeakSet

from seamless import Checksum
from seamless.util.source import strip_decorators

from . import SeamlessBase
from .status import StatusReasonEnum

cell_counter = 0

NoneChecksum = Checksum(None)


class Cell(SeamlessBase):
    """Default class for cells."""

    _celltype = None
    _subcelltype = None
    _checksum = NoneChecksum
    _void = True
    _status_reason = StatusReasonEnum.UNDEFINED
    _prelim = False
    _initial_val = None
    _initial_checksum = None
    _unmounted = False

    _mount = None
    _mount_kwargs = None
    _paths = None  # WeakSet of Path object weakrefs
    _hash_pattern = None  # must be None, except for MixedCell
    _subchecksums_persistent = False  # for deep cells
    _observer = None
    _traitlets = None
    _share = None
    _structured_cell = None
    _scratch = False

    """Parameters for putting the checksum 'at your fingertips':
    If "fingertip_recompute":
    - If not available, try to re-compute it using its provenance,
        i.e. re-evaluating any transformation or expression that produced it
    - Such recomputation is done in "fingertip" mode, i.e. disallowing
        use of expression-to-checksum or transformation-to-checksum caches
    If "fingertip_remote":
    - Verify that the buffer is locally or remotely available;
        if remotely, download it.
    """

    _fingertip_remote = True
    _fingertip_recompute = True

    def __init__(self):
        global cell_counter
        super().__init__()
        cell_counter += 1
        self._counter = cell_counter
        self._paths = WeakSet()
        self._traitlets = []

    @property
    def scratch(self):
        return self._scratch

    @property
    def _in_structured_cell(self):
        if self._structured_cell is None:
            return False
        if self._structured_cell.schema is self:
            return False
        return True

    def _set_context(self, ctx, name):
        assert not self._checksum
        has_ctx = self._context is not None
        super()._set_context(ctx, name)
        assert self._context() is ctx
        manager = self._get_manager()
        if not has_ctx:
            manager.register_cell(self)
        if self._initial_val is not None:
            value, from_buffer = self._initial_val
            if from_buffer:
                self.set_buffer(value)
            else:
                self.set(value)
            self._initial_val = None
        elif self._initial_checksum is not None:
            checksum, initial, from_structured_cell = self._initial_checksum
            self._set_checksum(checksum, initial, from_structured_cell)
            self._initial_checksum = None
        if not get_macro_mode():
            if self._mount is not None:
                mountmanager = manager.mountmanager
                mountmanager.scan(ctx._root())

    @property
    def celltype(self):
        return self._celltype

    def __hash__(self):
        return self._counter

    def __str__(self):
        ret = "Seamless %s cell: " % self._celltype + self._format_path()
        return ret

    def _get_status(self):
        from .status import status_cell, format_status

        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        status = status_cell(self)
        return status

    @property
    def status(self):
        """The cell's current status."""
        from .status import format_status

        status = self._get_status()
        statustxt = format_status(status)
        return "Status: " + statustxt

    @property
    def checksum(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        checksum = manager.get_cell_checksum(self)
        return checksum

    @property
    def void(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        void = manager.get_cell_void(self)
        return void

    @property
    def semantic_checksum(self):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        checksum = bytes.fromhex(self.checksum)
        transformation_cache = manager.cachemanager.transformation_cache
        sem_checksum = transformation_cache.syntactic_to_semantic(
            checksum, self._celltype, self._subcelltype, str(self)
        )
        return sem_checksum.hex()

    @property
    def buffer(self):
        """Return the cell's buffer.
        The cell's checksum is the SHA3-256 hash of this."""
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        buffer, _ = manager.get_cell_buffer_and_checksum(self)
        return buffer

    @property
    def buffer_and_checksum(self):
        """Return the cell's buffer and checksum."""
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        buffer, checksum = manager.get_cell_buffer_and_checksum(self)
        return buffer, checksum

    def _get_value(self, copy):
        manager = self._get_manager()
        if isinstance(manager, UnboundManager):
            raise Exception(
                "Cannot ask the cell value of a context that is being constructed by a macro"
            )
        return manager.get_cell_value(self, copy=copy)

    @property
    def value(self):
        """Returns a copy of the cell's value
        In case of deep cells, the underlying checksums are expanded to values
        cell.set(cell.value) is guaranteed to have no effect"""
        return self._get_value(copy=True)

    @property
    def data(self):
        """Returns the cell's value, without making a copy
        In case of deep cells, the underlying checksums are NOT expanded to values
        cell.set(cell.data) is NOT guaranteed to have no effect"""
        return self._get_value(copy=False)

    @property
    def exception(self):
        manager = self._get_manager()
        livegraph = manager.livegraph
        exc = livegraph.cell_parsing_exceptions.get(self)
        if exc is not None:
            return exc
        accessor = livegraph.cell_to_upstream.get(self)
        if accessor is None:
            return None
        expression = accessor.expression
        if expression is None:
            return None
        return expression.exception

    def set(self, value):
        """Update cell data from authority"""
        if self._context is None:
            self._initial_checksum = None
            self._initial_val = value, False
        else:
            manager = self._get_manager()
            manager.set_cell(self, value)
        return self

    def set_buffer(self, buffer, checksum=None):
        """Update cell buffer from authority.
        If the checksum is known, it can be provided as well."""
        if not (buffer is None or isinstance(buffer, bytes)):
            raise TypeError(type(buffer))
        if self._context is None:
            self._initial_checksum = None
            self._initial_val = buffer, True
        else:
            manager = self._get_manager()
            manager.set_cell_buffer(self, buffer, checksum)
        return self

    def _set_checksum(
        self, checksum: Checksum, initial=False, from_structured_cell=False
    ):
        """Specifies the checksum of the data (hex format)

        If "initial" is True, it is assumed that the context is being initialized (e.g. when created from a graph).
        Else, cell cannot be the .data or .buffer attribute of a StructuredCell, and cannot have any incoming connection.

        However, if "from_structured_cell" is True, then the cell is updated by its encapsulating structured cell
        """
        if self._context is None:
            self._initial_val = None
            if checksum:
                self._initial_checksum = checksum, initial, from_structured_cell
        else:
            manager = self._get_manager()
            manager.set_cell_checksum(
                self,
                checksum,
                initial=initial,
                from_structured_cell=from_structured_cell,
                trigger_bilinks=(not initial),
            )
        return self

    def set_checksum(self, checksum: str):
        """Specifies the checksum of the data (hex format), from authority"""
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
        """connects the cell to a target

        Target can be a cell, pin, inchannel or unilink"""
        from .worker import InputPin, EditPin, OutputPin
        from .transformer import Transformer
        from .macro import Macro, Path
        from .unilink import UniLink

        manager = self._get_manager()
        target_subpath = None

        if isinstance(target, UniLink):
            target = target.get_linked()

        if isinstance(target, Inchannel):
            target_subpath = target.subpath
            target = target.structured_cell().buffer
        elif isinstance(target, Outchannel):
            raise TypeError(
                "Outchannels must be the source of a connection, not the target"
            )

        if isinstance(target, Cell):
            if target_subpath is None:
                assert not target._structured_cell
        elif isinstance(target, Path):
            pass
        elif isinstance(target, InputPin):
            pass
        elif isinstance(target, EditPin):
            pass
        elif isinstance(target, OutputPin):
            raise TypeError(
                "Output pins must be the source of a connection, not the target"
            )
        elif isinstance(target, Transformer):
            raise TypeError("Transformers cannot be connected directly, select a pin")
        elif isinstance(target, Macro):
            raise TypeError("Macros cannot be connected directly, select a pin")
        else:
            raise TypeError(type(target))
        manager.connect(self, None, target, target_subpath)
        return self

    def connect_from(self, source):
        """connects the cell from a source

        Target can be a cell, pin, outchannel or unilink"""
        source.connect(self)
        return self

    def bilink(self, target):
        """Create a bidirectional unilink between two cells"""
        from .unilink import UniLink
        from .macro import Path

        if isinstance(target, UniLink):
            target = target.get_linked()
        if not isinstance(target, (Cell, Path)):
            raise TypeError(type(target))
        manager = self._get_manager()
        manager.bilink(self, target)

    def has_independence(self, path=None, *, manager=None):
        if manager is None:
            manager = self._get_manager()
        return manager.livegraph.has_independence(self, path)

    def upstream(self):
        manager = self._get_manager()
        accessor = manager.livegraph.cell_to_upstream.get(self)
        if accessor is None:
            return None
        return manager.livegraph.accessor_to_upstream.get(accessor)

    def set_file_extension(self, extension):
        if self._mount is None:
            self._mount = {}
        self._mount.update({"extension": extension})
        return self

    def mount(
        self,
        path=None,
        mode="rw",
        authority="file",
        *,
        persistent=True,
        as_directory=False,
        directory_text_only=False,
    ):
        """Performs a "lazy mount"; cell is mounted to the file when macro mode ends
        path: file path (can be None if an ancestor context has been mounted)
        mode: "r", "w" or "rw"
        authority: "cell", "file" or "file-strict"
        persistent: whether or not the file persists after the context has been destroyed
        as_directory: mount as directory
        directory_text_only: directory mount is text-only
        """
        from .context import Context

        assert is_dummy_mount(
            self._mount
        )  # Only the mountmanager may modify this further!
        if self._mount_kwargs is None:
            raise NotImplementedError  # cannot mount this type of cell

        kwargs = self._mount_kwargs
        if self._mount is None:
            self._mount = {}
        self._mount.update(
            {
                "autopath": False,
                "path": path,
                "mode": mode,
                "authority": authority,
                "persistent": persistent,
                "as_directory": as_directory,
                "directory_text_only": directory_text_only,
            }
        )
        self._mount.update(self._mount_kwargs)
        MountItem(None, self, dummy=True, **self._mount)  # to validate parameters
        context = self._context
        if context is not None and context() is not None:
            if isinstance(context(), Context):
                manager = context()._manager
                if manager is not None:
                    if not get_macro_mode():
                        mountmanager = manager.mountmanager
                        mountmanager.scan(context()._root())
        return self

    def _add_traitlet(self, traitlet, trigger=True):
        from ..highlevel.SeamlessTraitlet import SeamlessTraitlet

        assert isinstance(traitlet, SeamlessTraitlet)
        self._traitlets.append(traitlet)
        if trigger and self._checksum:
            traitlet.receive_update(self._checksum)

    def _set_observer(self, observer, trigger=True):
        manager = self._get_manager()
        livegraph = manager.livegraph
        self._observer = observer
        if trigger and self._checksum:
            cs = self._checksum
            if livegraph._hold_observations:
                livegraph._observing.append((self, cs))
            else:
                observer(cs)

    def share(
        self, path=None, readonly=True, mimetype=None, *, toplevel=False, cellname=None
    ):
        if not readonly:
            if (
                self._structured_cell is not None
                and self._structured_cell._data is self
            ):
                pass
            else:
                assert self.has_independence()
        oldshare = self._share
        self._share = {"readonly": readonly, "path": path, "toplevel": toplevel}
        if mimetype is not None:
            self._share["mimetype"] = mimetype
        if cellname is not None:
            self._share["cellname"] = cellname
        if oldshare != self._share:
            sharemanager.update_share(self)

    def unshare(self):
        if self._share is not None:
            sharemanager.unshare(self)

    def destroy(self, *, from_del=False, manager=None):
        if self._destroyed:
            return
        self.unshare()
        super().destroy(from_del=from_del)
        if manager is None:
            manager = self._get_manager()
        self._unmount(from_del=from_del, manager=manager)
        if not isinstance(manager, UnboundManager):
            manager._destroy_cell(self)
        for path in list(self._paths):
            path._bind(None, trigger=True)

    def _unmount(self, *, from_del, manager):
        from .macro import Macro

        if self._unmounted:
            return
        self._unmounted = True
        if isinstance(manager, UnboundManager):
            return
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

    def __init__(self, hash_pattern=None):
        from seamless.checksum.expression import validate_hash_pattern

        super().__init__()
        if hash_pattern is not None:
            validate_hash_pattern(hash_pattern)
            self._hash_pattern = hash_pattern

    @property
    def storage(self):

        v = super().value
        if v is None:
            return None
        return get_form(v)[0]

    @property
    def form(self):

        v = super().value
        if v is None:
            return None
        return get_form(v)[1]

    @property
    def value(self):
        """Returns a copy of the cell's value
        Deep structures are unfolded
        cell.set(cell.value) is guaranteed to have no effect"""
        from .protocol.expression import get_subpath_sync

        value = self._get_value(copy=True)
        if self._hash_pattern is None:
            return value
        # TODO: verify that the unfolded deep structure is not humongous...
        return get_subpath_sync(value, self._hash_pattern, None)


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
        """Update cell data from authority"""
        if callable(value):
            value = inspect.getsource(value)
        if value is not None:
            value = textwrap.dedent(value)
            value = strip_decorators(value)
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

    def set(self, value):
        """Update cell data from authority"""

        if callable(value):
            value = inspect.getsource(value)
        if value is not None:
            value = textwrap.dedent(value)
            value = strip_decorators(value)
        return super().set(value)

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

    _mount_kwargs = {"binary": True}
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


class ChecksumCell(TextCell):
    """A cell that contains a checksum hex, or a deep (Merkle-like) structure

    Checksum cells do not hold references to the checksum value(s) they contain
    """

    _celltype = "checksum"


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
    "checksum": ChecksumCell,
}


def cell(celltype="mixed", **kwargs):
    if celltype is None:
        celltype = "mixed"
    cellclass = cellclasses[celltype]
    return cellclass(**kwargs)


_cellclasses = [
    cellclass
    for cellclass in globals().values()
    if isinstance(cellclass, type) and issubclass(cellclass, Cell)
]

extensions = {cellclass: ".txt" for cellclass in _cellclasses}
extensions.update(
    {
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
    }
)

subcelltypes = {
    cellclass._subcelltype: cellclass
    for cellclass in _cellclasses
    if cellclass._subcelltype is not None
}
subcelltypes["module"] = None

from .unbound_context import UnboundManager
from .mount import MountItem
from .mount import is_dummy_mount
from silk.mixed.get_form import get_form
from .structured_cell import Inchannel, Outchannel
from .macro_mode import get_macro_mode
from .share import sharemanager

"""
TODO Documentation: only-text changes
     adding comments / breaking up lines to a Python cell will affect a syntax highlighter, but not a transformer, it is only text
     (a refactor that changes variable names would still trigger transformer re-execution, but this is probably the correct thing to do anyway)
     Same for CSON cells: if the CSON is changed but the corresponding JSON stays the same, the checksum stays the same.
     But the text checksum changes, and a text cell or text inputpin will receive an update.
"""

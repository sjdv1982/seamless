import weakref


class Accessor:
    pass


class ReadAccessor(Accessor):
    _checksum = (
        None  # accessors do not hold references to their checksums. Expressions do.
    )
    _void = True
    _status_reason = None
    _new_macropath = False  # if source or target is a newly bound macropath
    _prelim = False  # if accessor represents a preliminary result
    exception = None

    def __init__(self, source, manager, path, celltype, *, hash_pattern):
        self.source = source
        self.manager = weakref.ref(manager)
        self.path = path
        assert celltype in celltypes or isinstance(celltype, MacroPath), celltype
        self.reactor_pinname = None
        self.celltype = celltype
        self.write_accessor = None
        self.expression = None
        self._status_reason = StatusReasonEnum.UNDEFINED
        if isinstance(celltype, MacroPath):
            assert hash_pattern is None
        else:
            if hash_pattern is not None:
                assert celltype == "mixed"
            self.hash_pattern = hash_pattern

    @property
    def preliminary(self):
        return self._prelim

    def build_expression(self, livegraph, checksum):
        celltype = self.celltype
        if isinstance(celltype, MacroPath):
            macropath = celltype
            if macropath._cell is None:
                self.clear_expression(livegraph)
                return
            celltype = macropath._cell._celltype
            hash_pattern = macropath._cell._hash_pattern
        else:
            hash_pattern = self.hash_pattern
        target_celltype = self.write_accessor.celltype
        target_subcelltype = self.write_accessor.subcelltype
        if isinstance(target_celltype, MacroPath):
            macropath = target_celltype
            if macropath._cell is None:
                self.clear_expression(livegraph)
                return
            target_celltype = macropath._cell._celltype
            target_subcelltype = macropath._cell._subcelltype
        target = self.write_accessor.target()
        path = self.write_accessor.path
        target_hash_pattern = access_hash_pattern(
            self.write_accessor.hash_pattern, path
        )
        expression = Expression(
            checksum,
            self.path,
            celltype,
            target_celltype,
            target_subcelltype,
            hash_pattern=hash_pattern,
            target_hash_pattern=target_hash_pattern,
        )
        if self.expression is not None:
            if expression == self.expression:
                return
            livegraph.decref_expression(self.expression, self)
        self.expression = expression
        livegraph.incref_expression(expression, self)

    def clear_expression(self, livegraph):
        if self.expression is None:
            return
        livegraph.decref_expression(self.expression, self)
        self.expression = None

    def __repr__(self):
        result = "Accessor: " + str(self.source)
        if self.write_accessor is not None:
            result += " => " + str(self.write_accessor.target())
        return result

    def _root(self):
        return self.source._root()


class WriteAccessor(Accessor):
    def __init__(
        self,
        read_accessor,
        target,
        celltype,
        subcelltype,
        pinname,
        path,
        *,
        hash_pattern
    ):
        from ...core.cell import Cell
        from ...core.worker import Worker

        assert isinstance(read_accessor, ReadAccessor)
        assert isinstance(target, (Cell, Worker, MacroPath))
        assert pinname is None or path is None
        self.read_accessor = weakref.ref(read_accessor)
        self.target = weakref.ref(target)
        assert celltype in celltypes or isinstance(celltype, MacroPath), celltype
        self.celltype = celltype
        assert subcelltype is None or subcelltype in subcelltypes
        self.subcelltype = subcelltype
        self.pinname = pinname
        self.path = path
        if hash_pattern is not None:
            assert celltype == "mixed"
        self.hash_pattern = hash_pattern


from seamless.checksum.celltypes import celltypes
from ...core.cell import Cell, subcelltypes
from ...core.macro import Path as MacroPath
from ...core.status import StatusReasonEnum
from seamless.checksum import Expression
from seamless.checksum.expression import access_hash_pattern

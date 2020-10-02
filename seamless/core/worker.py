import weakref
from . import SeamlessBase
from .status import StatusReasonEnum

def _cell_from_pin(self, celltype):
    assert isinstance(self, (InputPin, EditPin))
    worker = self.worker_ref()
    if worker is None:
        raise ValueError("Worker has died")
    manager = self._get_manager()
    my_cell = manager.cell_from_pin(self)
    if celltype is None:
        celltype = self.celltype
    if my_cell is None:
        my_cell = cell(celltype)
        ctx = worker._context
        assert ctx is not None
        ctx = ctx()
        ctx._add_new_cell(my_cell)
        manager.connect(my_cell, None, self, None)
    else:
        # TODO: take subpath (my_cell[1]) into account? construct some kind of proxy?
        if isinstance(self, EditPin):
            if not len(my_cell):
                my_cell = None
            else:
                my_cell = my_cell[0]
        else:
            my_cell = my_cell[0]
    if isinstance(my_cell, Path):
        my_cell = my_cell._cell
    if my_cell is None:
        return None
    assert isinstance(my_cell, Cell), type(my_cell)
    return my_cell


class Worker(SeamlessBase):
    """Base class for all workers."""
    _void = True
    _status_reason = StatusReasonEnum.UNCONNECTED
    _pins = None
    _last_inputs = None

    def __getattr__(self, attr):
        if self._pins is None or attr not in self._pins:
            raise AttributeError(attr)
        else:
            return self._pins[attr]


    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())


from .cell import celltypes as celltypes0
celltypes = list(celltypes0) + ["module"]

class PinBase(SeamlessBase):
    def __init__(self, worker, name, celltype, subcelltype=None):
        self.worker_ref = weakref.ref(worker)
        super().__init__()
        assert celltype is None or celltype in celltypes, (celltype, celltypes)
        self.name = name
        self.celltype = celltype
        self.subcelltype = subcelltype

    @property
    def path(self):
        worker = self.worker_ref()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if worker is None:
            return ("<None>",) + name
        return worker.path + name

    @property
    def _context(self):
        worker = self.worker_ref()
        if worker is None:
            return None
        return worker._context

    def _get_macro(self):
        return self._context()._macro


class InputPinBase(PinBase):
    def _set_context(self, context, childname):
        pass
    def __str__(self):
        ret = "Seamless input pin: " + self._format_path()
        return ret

class OutputPinBase(PinBase):
    def _set_context(self, context, childname):
        pass
    def __str__(self):
        ret = "Seamless output pin: " + self._format_path()
        return ret

class InputPin(InputPinBase):
    """Connects cells to workers (transformers and reactor)

    cell.connect(pin) connects a cell to an inputpin
    pin.cell() returns or creates a cell that is connected to the inputpin
    """
    io = "input"
    _hash_pattern = None

    def cell(self, celltype=None):
        """Returns or creates a cell connected to the inputpin"""
        return _cell_from_pin(self, celltype)

    def set(self, *args, **kwargs):
        """Sets the value of the connected cell"""
        return self.cell().set(*args, **kwargs)


class OutputPin(OutputPinBase):
    """Connects the output of workers (transformers and reactors) to cells

    outputpin.connect(cell) connects an outputpin to a cell
    outputpin.cell() returns or creates a cell that is connected to the outputpin
    """
    io = "output"
    _hash_pattern = None

    def connect(self, target):
        """connects the pin to a target"""
        from .transformer import Transformer
        from .reactor import Reactor
        from .macro import Macro, Path
        from .unilink import UniLink

        manager = self._get_manager()

        if isinstance(target, UniLink):
            target = target.get_linked()

        target_subpath = None
        if isinstance(target, Inchannel):
            target_subpath = target.subpath
            target = target.structured_cell().buffer
        elif isinstance(target, Outchannel):
            raise TypeError("Outchannels must be the source of a connection, not the target")

        if isinstance(target, Path):
            raise TypeError("Workers may not connect to paths")

        if isinstance(target, Cell):
            assert not target._structured_cell
        elif isinstance(target, PinBase):
            raise TypeError("Pin-pin connections are not allowed, create a cell")
        elif isinstance(target, Transformer):
            raise TypeError("Transformers cannot be targeted by pins")
        elif isinstance(target, Reactor):
            raise TypeError("Reactors cannot be targeted by pins")
        elif isinstance(target, Macro):
            raise TypeError("Macros cannot be targeted by pins")
        else:
            raise TypeError(type(target))

        manager.connect(self, None, target, target_subpath)
        return self

    def cell(self, celltype=None):
        """returns or creates a cell that is connected to the pin"""
        from .cell import cell
        manager = self._get_manager()
        my_cells = manager.cell_from_pin(self)
        celltype = self.celltype
        l = len(my_cells) if my_cells is not None else 0
        if l == 0:
            worker = self.worker_ref()
            if worker is None:
                raise ValueError("Worker has died")
            my_cell = cell(celltype)
            ctx = worker._context
            assert ctx is not None
            ctx = ctx()
            ctx._add_new_cell(my_cell)
            assert my_cell._context() is ctx
            manager.connect(self, None, my_cell, None)
        elif l == 1:
            # TODO: take subpath into account? construct some kind of proxy?
            my_cell, subpath = my_cells[0]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        return my_cell

    def cells(self):
        """Returns all cell/subpath tuples connected to the outputpin"""
        manager = self._get_manager()
        my_cells = manager.cell_from_pin(self)
        # TODO: take subpath (c[1]) into account? construct some kind of proxy?
        if my_cells is None:
            return []
        my_cells = [c[0] for c in my_cells]
        return mycells


class EditPinBase(PinBase):
    def _set_context(self, context, childname):
        pass

    def cell(self, celltype=None):
        """Returns the cell connected to the editpin"""
        return _cell_from_pin(self, celltype)

    def __str__(self):
        ret = "Seamless editpin: " + self._format_path()
        return ret

class EditPin(EditPinBase):
    """Connects a cell as both the input and output of a reactor

    editpin.connect(cell), cell.connect(editpin):
      connects the editpin to a cell
    editpin.cell() returns or creates a cell that is connected to the editpin
    outputpin.disconnect(cell) breaks an existing connection
    """

    io = "edit"

    def set(self, *args, **kwargs):
        """Sets the value of the connected cell"""
        return self.cell().set(*args, **kwargs)

    def connect(self, target):
        """connects the pin to a target"""
        from .transformer import Transformer
        from .reactor import Reactor
        from .macro import Macro, Path
        from .unilink import UniLink

        manager = self._get_manager()

        if isinstance(target, UniLink):
            target = target.get_linked()

        assert not isinstance(target, Path) #Edit pins cannot be connected to paths

        if isinstance(target, Inchannel):
            raise TypeError("Inchannels cannot be connected to edit pins, only to output pins")
        elif isinstance(target, Outchannel):
            raise TypeError("Outchannels must be the source of a connection, not the target")

        if isinstance(target, Cell):
            assert not target._structured_cell
        elif isinstance(target, PinBase):
            raise TypeError("Pin-pin connections are not allowed, create a cell")
        elif isinstance(target, Transformer):
            raise TypeError("Transformers cannot be targeted by pins")
        elif isinstance(target, Reactor):
            raise TypeError("Reactors cannot be targeted by pins")
        elif isinstance(target, Macro):
            raise TypeError("Macros cannot be targeted by pins")
        else:
            raise TypeError(type(target))

        manager.connect(self, None, target, None)
        return self

    @property
    def status(self):
        from .status import status_accessor, format_status
        from .transformer import Transformer
        manager = self._get_manager()
        livegraph = manager.livegraph
        worker = self.worker_ref()
        if isinstance(worker, Transformer):
            upstreams = livegraph.transformer_to_upstream[worker]
            accessor = upstreams[self.name]
        else:
            raise NotImplementedError # reactor, macro accessor status
        stat = status_accessor(accessor)
        return format_status(stat)

from .structured_cell import Inchannel, Outchannel
from .cell import cell, Cell
from .macro import Path

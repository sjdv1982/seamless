import weakref
from . import SeamlessBase

def _cell_from_pin(self, celltype):    
    assert isinstance(self, (InputPin, EditPin))
    from .cell import cell, Cell
    from .macro import Path
    manager = self._get_manager()
    my_cell = manager.cell_from_pin(self)
    if celltype is None:
        celltype = self.content_type # for now, a 1:1 correspondence between content type and cell type
        if celltype is None:
            celltype = default_cell_types.get(self.access_mode, "plain")
    if my_cell is None:
        worker = self.worker_ref()
        if worker is None:
            raise ValueError("Worker has died")
        my_cell = cell(celltype)
        ctx = worker._context
        assert ctx is not None
        ctx = ctx()
        ctx._add_new_cell(my_cell)
        manager.connect_cell(my_cell, self, None)
    else:
        # TODO: take subpath (my_cell[1]) into account? construct some kind of proxy?
        if isinstance(self, EditPin):
            if not len(my_cell):
                my_cell = None
            else:
                my_cell = my_cell[0]
    if my_cell is None:
        return my_cell
    if isinstance(my_cell, Cell):
        return my_cell
    elif isinstance(my_cell, Path):
        return my_cell._cell
    else: # Accessor
        return my_cell.cell


class Worker(SeamlessBase):
    """Base class for all workers."""
    _pins = None
    _active = True

    def __getattr__(self, attr):
        if self._pins is None or attr not in self._pins:
            raise AttributeError(attr)
        else:
            return self._pins[attr]

    def touch(self):
        raise NotImplementedError ###cache branch, also see BAK/[transformer/macro/reactor].py _touch
        """
        manager = self._get_manager()
        manager.touch_worker(self)
        """

    @property
    def debug(self):
        raise NotImplementedError ###cache branch

    @debug.setter
    def debug(self, value):        
        assert isinstance(value, bool), value
        raise NotImplementedError ###cache branch
        """
        old_value = self.transformer.debug
        if value != old_value:            
            self.transformer.debug = value
            manager = self._get_manager()
            manager.touch_worker(self)
        """
    
    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())


    @property
    def status(self):
        """The computation status of the worker"""
        return self._get_manager().status[self]


from .protocol import transfer_modes, access_modes, content_types

default_cell_types = {
    "pythoncode": "python",
    "plain": "plain",
    "silk": "plain",
    "default": "plain",
    "text": "text",
    "module": "python",
}
class PinBase(SeamlessBase):
    access_mode = None
    def __init__(self, worker, name, transfer_mode, access_mode=None, content_type=None):
        self.worker_ref = weakref.ref(worker)
        super().__init__()
        assert transfer_mode in transfer_modes, (transfer_mode, transfer_modes)
        if transfer_mode == "module":
            assert access_mode is None
            assert content_type is None
        if access_mode is not None:
            if isinstance(self, InputPin):
                assert access_mode in access_modes + ("default",), (access_mode, access_modes)
            else:
                assert access_mode in access_modes, (access_mode, access_modes)
        self.name = name
        self.transfer_mode = transfer_mode
        if content_type is not None:
            assert content_type in content_types, (content_type, content_types)
        self.content_type = content_type
        if access_mode is not None:
            self.access_mode = access_mode

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

    def connect(self, target):
        """connects to a target cell"""
        manager = self._get_manager()
        manager.connect_pin(self, target)
        return self

    def cell(self, celltype=None):
        """returns or creates a cell that is connected to the pin"""
        from .cell import cell
        manager = self._get_manager()
        my_cells = manager.cell_from_pin(self)
        if celltype is None:
            celltype = self.content_type # for now, a 1:1 correspondence between content type and cell type
            if celltype is None:
                celltype = default_cell_types.get(self.access_mode, "plain")
        l = len(my_cells)
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
            manager.connect_pin(self, my_cell)
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
        my_cells = [c[0] for c in my_cells]
        return mycells

    @property
    def status(self):
        manager = self._get_manager()
        raise NotImplementedError ###cache branch
        my_cells = manager.pin_to_cells.get(self, [])
        if len(my_cells):
            my_cell = my_cells[0]
            return my_cell.target.status()
        else:
            return self.StatusFlags.UNCONNECTED.name

class EditPinBase(PinBase):
    def _set_context(self, context, childname):
        pass

    def cell(self, celltype=None):
        """Returns or creates a cell connected to the editpin"""
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
        """connects to a target cell"""
        raise NotImplementedError ###cache branch
        ###manager = self._get_manager()
        ###manager.connect_pin(self, target)  #NO; double connection has to be made
                                              #connect_cell will also invoke connect_pin
        assert not isinstance(target, Path) #Edit pins cannot be connected to paths
        other = target._get_manager()
        other.connect_cell(target, self, None, None)
        return self

    @property
    def status(self):
        manager = self._get_manager()
        raise NotImplementedError ###cache branch
        my_cells = manager.pin_to_cells.get(self, [])
        if len(my_cells):
            my_cell = my_cells[0].target
            return my_cell.status()
        else:
            return self.StatusFlags.UNCONNECTED.name

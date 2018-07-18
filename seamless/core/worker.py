import weakref
from . import SeamlessBase
from . import get_macro_mode
from .cell import modes as cell_modes, submodes as cell_submodes

"""
Evaluation modes for workers
They are the same as at mid-level
More fancy stuff (such as services and seamless-to-seamless communication
 over the network) has to be organized at the high level
"""
mode = ["sync", "async"]
submode = {
    "sync": ["inline"],
    "async": ["thread", "subprocess"]
}

class Worker(SeamlessBase):
    """Base class for all workers."""
    _pins = None
    _naming_pattern = "worker"

    def __init__(self):
        assert get_macro_mode()
        super().__init__()
        self._pending_updates_value = 0
        self._last_update_checksums = {}

    def _receive_update_checksum(self, pin, checksum):
        if pin not in self._last_update_checksums:
            if checksum is not None:
                self._last_update_checksums[pin] = checksum
            return True
        curr = self._last_update_checksums[pin]
        if curr == checksum:
            return False
        if checksum is not None:
            self._last_update_checksums[pin] = checksum
        return True

    def activate(self, only_macros):
        try:
            from ..shell import update_shells
        except ImportError:  ### If qt is not there...
            return
        shell_namespace, inputpin, _ = self._shell(None)
        update_shells(inputpin, shell_namespace)

    @property
    def _seal(self):
        ctx = self._context()
        assert ctx is not None
        return ctx._seal

    @property
    def _pending_updates(self):
        return self._pending_updates_value

    @_pending_updates.setter
    def _pending_updates(self, value):
        manager = self._get_manager()
        old_value = self._pending_updates_value
        if old_value == 0 and value > 0:
            manager.set_stable(self, False)
        if old_value > 0 and value == 0:
            manager.set_stable(self, True)
        self._pending_updates_value = value

    def __getattr__(self, attr):
        if self._pins is None or attr not in self._pins:
            raise AttributeError(attr)
        else:
            return self._pins[attr]

    def receive_update(self, input_pin, value, checksum):
        raise NotImplementedError

    def touch(self):
        manager = self._get_manager()
        manager.touch_worker(self)

    def _validate_path(self, required_path=None):
        required_path = super()._validate_path(required_path)
        for pin_name, pin in self._pins.items():
            pin._validate_path(required_path + (pin_name,))
        return required_path

    def shell(self, subshell=None):
        """Creates an IPython shell (QtConsole).

        The shell is connected to the namespace of a worker (reactor
        or transformer, or a context that has a worker exported)
        where its code blocks are executed.

        This works only for in-process workers. As of seamless 0.1, all workers are
        in-process. However, transformers use ``multiprocessing``. Therefore, changes
        to the namespace while a transformation is running will not affect the current
        transformation, only the next.

        As of seamless 0.2, a reactor's namespace is reset upon ``code_start``.
        A transformer's namespace is reset upon every execution.

        TODO: further description
        subshell must be None for transformers, "start"/"update"/"stop" for reactors
        """
        #TODO: for serialization, store associated shells

        from ..shell import PyShell
        shell_namespace, inputpin, shell_title = self._shell(subshell)
        return PyShell(shell_namespace, inputpin, shell_title)

    def full_destroy(self, from_del=False):
        raise NotImplementedError

from .cell import modes as cell_modes, submodes as cell_submodes, celltypes

class PinBase(SeamlessBase):
    submode = None
    def __init__(self, worker, name, mode, submode=None, celltype=None):
        self.worker_ref = weakref.ref(worker)
        super().__init__()
        assert mode in cell_modes, (mode, cell_modes)
        if submode is not None:
            assert submode in cell_submodes[mode], (mode, cell_submodes)
        self.name = name
        self.mode = mode
        if celltype is not None:
            assert celltype in celltypes, (celltype, celltypes)
        self.celltype = celltype
        if submode is not None:
            self.submode = submode

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

    def get_pin(self):
        return self

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

    def cell(self, celltype=None):
        """Returns or creates a cell connected to the inputpin"""
        from .cell import cell
        manager = self._get_manager()
        my_cell = manager.pin_from_cell.get(self)
        if celltype is None:
            celltype = self.celltype
        if my_cell is None:
            worker = self.worker_ref()
            if worker is None:
                raise ValueError("Worker has died")
            my_cell = cell(celltype)
            ctx = worker._context
            assert ctx is not None
            ctx = ctx()
            ctx._add_new_cell(my_cell)
            my_cell.connect(self)
        else:
            my_cell = my_cell[1]
        return my_cell

    def set(self, *args, **kwargs):
        """Sets the value of the connected cell"""
        return self.cell().set(*args, **kwargs)

    def receive_update(self, value, checksum):
        """Private"""
        worker = self.worker_ref()
        if worker is None:
            return #Worker has died...
        worker.receive_update(self.name, value, checksum)

    def status(self):
        manager = self._get_manager()
        my_cell = manager.pin_from_cell.get(self)
        if my_cell is not None:
            my_cell = my_cell[1]
            return my_cell.status()
        else:
            return self.StatusFlags.UNCONNECTED.name

    def _touch(self):
        raise NotImplementedError

class OutputPin(OutputPinBase):
    """Connects the output of workers (transformers and reactors) to cells

    outputpin.connect(cell) connects an outputpin to a cell
    outputpin.cell() returns or creates a cell that is connected to the outputpin
    """

    last_value = None

    def get_pin(self):
        """Private"""
        return self

    def send_update(self, value, *, preliminary=False):
        """Private"""
        self.last_value = value
        manager = self._get_manager()
        manager.pin_send_update(self, value, preliminary=preliminary)

    def connect(self, target):
        """connects to a target cell"""
        assert get_macro_mode() #or connection overlay mode, TODO
        manager = self._get_manager()
        manager.connect_pin(self, target)
        return self

    def cell(self, celltype=None):
        """returns or creates a cell that is connected to the pin"""
        from .cell import cell
        manager = self._get_manager()
        my_cells = manager.pin_to_cells.get(self, [])
        if celltype is None:
            celltype = self.celltype
        l = len(my_cells)
        if l == 0:
            worker = self.worker_ref()
            if worker is None:
                raise ValueError("Worker has died")
            my_cell = cell(celltype)
            self.connect(my_cell)
        elif l == 1:
            my_cell = my_cells[0]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        return my_cell[1]

    def cells(self):
        """Returns all cells connected to the outputpin"""
        manager = self._get_manager()
        my_cells = manager.pin_to_cells.get(self, [])
        return [c[1] for c in my_cells]

    def status(self):
        manager = self._get_manager()
        my_cells = manager.pin_to_cells.get(self, [])
        if len(my_cells):
            my_cell = my_cells[0][1]
            return my_cell.status()
        else:
            return self.StatusFlags.UNCONNECTED.name

class EditPinBase(PinBase):
    def _set_context(self, context, childname):
        pass

class EditPin(EditPinBase):
    """Connects a cell as both the input and output of a reactor

    editpin.connect(cell), cell.connect(editpin):
      connects the editpin to a cell
    editpin.cell() returns or creates a cell that is connected to the editpin
    outputpin.disconnect(cell) breaks an existing connection
    """

    last_value = None

    def cell(self, celltype=None):
        """Returns or creates a cell connected to the inputpin"""
        from .cell import cell
        manager = self._get_manager()
        my_cells = manager.editpin_to_cells(self)
        if celltype is None:
            celltype = self.celltype
        l = len(my_cells)
        if l == 0:
            worker = self.worker_ref()
            if worker is None:
                raise ValueError("Worker has died")
            my_cell = cell(celltype)
            my_cell.connect(self)
        elif l == 1:
            my_cell = my_cells[0]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        return my_cell

    def set(self, *args, **kwargs):
        """Sets the value of the connected cell"""
        return self.cell().set(*args, **kwargs)

    def connect(self, target):
        """connects to a target cell"""
        assert get_macro_mode() #or connection overlay mode, TODO
        manager = self._get_manager()
        manager.connect_pin(self, target)
        return self

    def send_update(self, value, *, preliminary=False):
        """Private"""
        self.last_value = value
        manager = self._get_manager()
        manager.pin_send_update(self, value, preliminary=preliminary)

    def receive_update(self, value, checksum):
        """Private"""
        worker = self.worker_ref()
        if worker is None:
            return #Worker has died...
        worker.receive_update(self.name, value, checksum)

    def status(self):
        manager = self._get_manager()
        my_cells = manager.pin_to_cells.get(self, [])
        if len(my_cells):
            my_cell = my_cells[0][1]
            return my_cell.status()
        else:
            return self.StatusFlags.UNCONNECTED.name

'''
class ExportedPinBase:
    def __init__(self, pin):
        self._pin = pin

    def _set_context(self, context, childname):
        self.name = childname

    def __getattr__(self, attr):
        return getattr(self._pin, attr)

    @property
    def context(self):
        return self._pin.context

    @property
    def path(self):
        return self._pin.path

    def _get_manager(self):
        return self._pin._get_manager()

class ExportedOutputPin(ExportedPinBase, OutputPinBase):
    def __init__(self, pin):
        assert isinstance(pin, OutputPinBase)
        super().__init__(pin)
    def cells(self):
        return self._pin.cells()
ExportedOutputPin.__doc__ = OutputPin.__doc__

class ExportedInputPin(ExportedPinBase, InputPinBase):
    def __init__(self, pin):
        assert isinstance(pin, InputPinBase)
        super().__init__(pin)
ExportedInputPin.__doc__ = InputPin.__doc__

class ExportedEditPin(ExportedPinBase, EditPinBase):
    def __init__(self, pin):
        assert isinstance(pin, EditPinBase)
        super().__init__(pin)
ExportedEditPin.__doc__ = EditPin.__doc__
'''

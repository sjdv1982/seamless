#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary
from . import SeamlessBase

class Managed(SeamlessBase):
    def _get_manager(self):
        context = self.context
        if context is None:
            raise Exception(
             "Cannot carry out requested operation without a context"
            )
        return context._manager

class ProcessLike:
    """Base class for processes and contexts"""
    _like_process = True

class Process(Managed, ProcessLike):
    """Base class for all processes."""
    _pins = None

    def __init__(self):
        super().__init__()
        from .macro import get_macro_mode
        from .context import get_active_context
        if get_macro_mode():
            ctx = get_active_context()
            assert self._context is None, self
            name = ctx._add_new_process(self)

    def destroy(self):
        print("PROCESS DESTROY", self)
        if self._destroyed:
            return
        for pin_name, pin in self._pins.items():
            pin.destroy()
        if self.context is not None:
            manager = self.context._manager
            manager.remove_registrar_listeners(self)
        super().destroy()

    def receive_update(self, input_pin, value):
        raise NotImplementedError

    def receive_registrar_update(self, registrar_name, key, namespace_name):
        raise NotImplementedError

    def _validate_path(self, required_path=None):
        required_path = super()._validate_path(required_path)
        for pin_name, pin in self._pins.items():
            pin._validate_path(required_path + (pin_name,))
        return required_path

class PinBase(Managed):

    def __init__(self, process, name):
        self.process_ref = weakref.ref(process)
        super().__init__()
        self.name = name

    def _set_context(self, context, force_detach=False):
        pass

    @property
    def path(self):
        process = self.process_ref()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if process is None:
            return (None,) + name
        return process.path + name

    @property
    def context(self):
        process = self.process_ref()
        if process is None:
            return None
        return process.context

    def get_pin_id(self):
        return id(self.get_pin())

    def get_pin(self):
        return self

    def _own(self):
        raise TypeError(type(self))

class InputPinBase(PinBase):

    def destroy(self):
        context = self.context
        if context is None:
            return
        super().destroy()
        manager = self._get_manager()
        manager.remove_listener(self)

class OutputPinBase(PinBase):

    def destroy(self):
        if self._destroyed:
            return
        #print("OUTPUTPIN DESTROY")
        context = self.context
        if context is None:
            return
        super().destroy()
        manager = context._manager
        for cell_id in list(self._cell_ids):
            cell = manager.cells.get(cell_id, None)
            if cell is None:
                continue
            cell._on_disconnect(self, self.process_ref(), True)


class InputPin(InputPinBase):

    def __init__(self, process, name, dtype):
        InputPinBase.__init__(self, process, name)
        self.dtype = dtype

    def cell(self, own=False):
        from .cell import cell
        from .context import active_owner_as, get_active_context
        from .macro import get_macro_mode
        manager = self._get_manager()
        context = self.context
        curr_pin_to_cells = manager.pin_to_cells.get(self.get_pin_id(), [])
        l = len(curr_pin_to_cells)
        if l == 0:
            if self.dtype is None:
                raise ValueError(
                 "Cannot construct cell() for pin with dtype=None"
                )
            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")
            with active_owner_as(self):
                my_cell = cell(self.dtype)
            if not get_macro_mode():
                ctx = get_active_context()
                if ctx is None:
                    ctx = context
                ctx._add_new_cell(my_cell)
            my_cell.connect(self)
        elif l == 1:
            my_cell = manager._childids[curr_pin_to_cells[0]]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        if own:
            self.own(my_cell)
        return my_cell

    def update(self, value):
        process = self.process_ref()
        if process is None:
            return #Process has died...

        process.receive_update(self.name, value)


class OutputPin(OutputPinBase):
    def __init__(self, process, name, dtype, liquid=False):
        OutputPinBase.__init__(self, process, name)
        self.dtype = dtype
        self.liquid = liquid
        self._cell_ids = []

    def get_pin(self):
        return self

    def update(self, value):
        manager = self._get_manager()
        for cell_id in self._cell_ids:
            manager.update_from_process(cell_id, value)

    def connect(self, target):
        manager = self._get_manager()
        manager.connect(self, target)

    def cell(self, own=False):
        from .cell import cell
        from .context import active_owner_as, get_active_context
        from .macro import get_macro_mode
        context = get_active_context()
        if context is None:
            context = self.context
        assert context is not None
        manager = context._manager
        l = len(self._cell_ids)
        if l == 0:
            if self.dtype is None:
                raise ValueError(
                 "Cannot construct cell() for pin with dtype=None"
                )
            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")
            with active_owner_as(self):
                my_cell = cell(self.dtype)
            if not get_macro_mode():
                ctx = get_active_context()
                if ctx is None:
                    ctx = context
                ctx._add_new_cell(my_cell)
            self.connect(my_cell)
        elif l == 1:
            my_cell = manager._childids[self._cell_ids[0]]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        if own:
            self.own(my_cell)
        return my_cell

    def cells(self):
        context = self.context
        manager = context._manager
        cells = [c for c in context.cells if manager.get_cell_id(c) in self._cell_ids]
        return cells


class EditorOutputPin(OutputPinBase):
    def __init__(self, process, name, dtype):
        OutputPinBase.__init__(self, process, name)
        self.solid = OutputPin(process, (name, "solid"), dtype)
        self.liquid = OutputPin(process, (name, "liquid"), dtype, liquid=True)

    @property
    def _cell_ids(self):
        return list(self.solid._cell_ids) + list(self.liquid._cell_ids)

    def get_pin(self):
        return self

    def update(self, value):
        self.solid.update(value)
        self.liquid.update(value)

    def connect(self, target):
        raise TypeError("Cannot connect EditorOutputPin, select .solid or .liquid")

    def cell(self):
        raise TypeError("Cannot obtain .cell for EditorOutputPin, select .solid or .liquid")

    def cells(self):
        raise TypeError("Cannot obtain .cells for EditorOutputPin, select .solid or .liquid")

    def destroy(self):
        if self._destroyed:
            return
        self.solid.destroy()
        self.liquid.destroy()
        super().destroy()

    def _validate_path(self, required_path=None):
        required_path = super()._validate_path(required_path)
        self.solid._validate_path(required_path + ("solid",))
        self.liquid._validate_path(required_path + ("liquid",))
        return required_path


class ExportedPinBase:
    def __init__(self, pin):
        self._pin = pin

    def get_pin_id(self):
        return self._pin.get_pin_id()

    def get_pin(self):
        return self._pin.get_pin()

    def __getattr__(self, attr):
        return getattr(self._pin, attr)

    def _set_context(self, context, force_detach=False):
        pass

    @property
    def context(self):
        return self._pin.context

    @property
    def path(self):
        return self._pin.path

    @property
    def name(self):
        return self._pin.name

    def own(self, *args, **kwargs):
        return self._pin.own(*args, **kwargs)

    def _get_manager(self):
        return self._pin._get_manager()

    def destroy(self):
        self._pin.destroy()

class ExportedOutputPin(ExportedPinBase, OutputPinBase):
    @property
    def _cell_ids(self):
        return self._pin._cell_ids

class ExportedInputPin(ExportedPinBase, InputPinBase):
    pass

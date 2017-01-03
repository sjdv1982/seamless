#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary
from . import SeamlessBase

#TODO: disconnect method (see MacroObject for low-level implementation)

class Manager:

    def __init__(self):
        self.listeners = {}
        self.macro_listeners = {}
        self.pin_to_cells = {}
        self.cells = WeakValueDictionary()
        super().__init__()

    def add_listener(self, cell, input_pin):
        cell_id = self.get_cell_id(cell)
        pin_ref = weakref.ref(input_pin)

        try:
            listeners = self.listeners[cell_id]
            assert pin_ref not in listeners
            # TODO: tolerate (silently ignore) a connection that exists already?
            listeners.append(pin_ref)

        except KeyError:
            self.listeners[cell_id] = [pin_ref]

        try:
            curr_pin_to_cells = self.pin_to_cells[input_pin.get_pin_id()]
            assert cell_id not in curr_pin_to_cells
            # TODO: tolerate (append) multiple inputs?
            curr_pin_to_cells.append(cell_id)

        except KeyError:
            self.pin_to_cells[input_pin.get_pin_id()] = [cell_id]

        if cell_id not in self.cells:
            self.cells[cell_id] = cell

    def remove_listener(self, input_pin):
        process = input_pin.process_ref()
        cell_ids = self.pin_to_cells.pop(input_pin.get_pin_id(), [])
        for cell_id in cell_ids:
            l = self.listeners[cell_id]
            l[:] = [ref for ref in l if ref().get_pin_id() != input_pin.get_pin_id()]
            if not len(l):
                self.listeners.pop(cell_id)
                cell = self.cells.get(cell_id, None)
                if cell is not None:
                    cell._on_disconnect(input_pin, process, False)

    def add_macro_listener(self, cell, macro_object, macro_arg):
        cell_id = self.get_cell_id(cell)
        macro_ref = weakref.ref(macro_object)
        m = (macro_ref, macro_arg)

        try:
            macro_listeners = self.macro_listeners[cell_id]
            assert m not in macro_listeners
            macro_listeners.append(m)

        except KeyError:
            self.macro_listeners[cell_id] = [m]

    def remove_macro_listener(self, cell, macro_object, macro_arg):
        cell_id = self.get_cell_id(cell)
        macro_ref = weakref.ref(macro_object)
        m = (macro_ref, macro_arg)

        if cell_id in self.macro_listeners:
            l = self.macro_listeners[cell_id]
            if m in l:
                l.remove(m)

    def _update(self, cell_id, value):
        macro_listeners = self.macro_listeners.get(cell_id, [])

        for macro_ref, macro_arg in macro_listeners:
            macro_object = macro_ref()

            if macro_object is None:
                continue #TODO: error?

            macro_object.update_cell(macro_arg)

        listeners = self.listeners.get(cell_id, [])
        for input_pin_ref in listeners:
            input_pin = input_pin_ref()

            if input_pin is None:
                continue #TODO: error?

            input_pin.update(value)


    def update_from_code(self, cell):
        value = cell._data
        cell_id = self.get_cell_id(cell)
        self._update(cell_id, value)

    def update_from_process(self, cell_id, value):
        cell = self.cells.get(cell_id, None)
        if cell is None:
            return #cell has died...

        changed = cell._update(value)
        if changed:
            self._update(cell_id, value)

    @classmethod
    def get_cell_id(cls, cell):
        return id(cell)

    def connect(self, source, target):
        from .transformer import Transformer
        from .cell import Cell, CellLike
        from .context import Context
        if isinstance(source, CellLike) and source._like_cell:
            assert isinstance(target, InputPinBase)
            assert source._get_manager() is self
            assert target._get_manager() is self
            if isinstance(target, ExportedInputPin):
                target = target.get_pin()

            if isinstance(source, Context):
                assert "_output" in source._pins
                source = source._pins["_output"]
            process = target.process_ref()
            assert process is not None #weakref may not be dead
            source._on_connect(target, process, incoming = False)
            self.add_listener(source, target)

            if source._status == Cell.StatusFlags.OK:
                self.update_from_code(source)

        elif isinstance(source, OutputPinBase):
            assert isinstance(target, CellLike) and target._like_cell
            if isinstance(target, Context):
                assert "_input" in target._pins
                target = target._pins["_input"]
            if isinstance(source, ExportedOutputPin):
                source = source.get_pin()
            process = source.process_ref()
            assert process is not None #weakref may not be dead
            target._on_connect(source, process, incoming = True)
            cell_id = self.get_cell_id(target)
            if cell_id not in self.cells:
                self.cells[cell_id] = target

            if cell_id not in source._cell_ids:
                source._cell_ids.append(cell_id)

            if isinstance(process, Transformer):
                process._on_connect_output()

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
        from .macro import get_macro_mode
        from .context import get_active_context
        if get_macro_mode():
            ctx = get_active_context()
            ctx._add_new_process(self)
        super().__init__()

    def destroy(self):
        #print("PROCESS DESTROY")
        if self._destroyed:
            return
        for pin_name, pin in self._pins.items():
            pin.destroy()
        super().destroy()

class PinBase(Managed):

    def __init__(self, process):
        self.process_ref = weakref.ref(process)
        super().__init__()

    def _set_context(self, context, force_detach=False):
        process = self.process_ref()
        if process is None:
            return #Process has died...
        process._set_context(context, force_detach)

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

    def __init__(self, process, identifier, dtype):
        InputPinBase.__init__(self, process)
        self.identifier = identifier
        self.dtype = dtype

    def cell(self, own=False):
        from .cell import cell
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
            my_cell = cell(self.dtype)
            context._add_new_cell(my_cell)
            my_cell.connect(self)
        elif l == 1:
            my_cell = context._childids[curr_pin_to_cells[0]]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        if own:
            self.own(my_cell)
        return my_cell

    def update(self, value):
        process = self.process_ref()
        if process is None:
            return #Process has died...

        process.receive_update(self.identifier, value)


class OutputPin(OutputPinBase):
    def __init__(self, process, identifier, dtype):
        OutputPinBase.__init__(self, process)
        self.identifier = identifier
        self.dtype = dtype
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

    def cell(self,own=False):
        from .cell import cell
        context = self.context
        assert context is not None
        l = len(self._cell_ids)
        if l == 0:
            if self.dtype is None:
                raise ValueError(
                 "Cannot construct cell() for pin with dtype=None"
                )
            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")
            my_cell = cell(self.dtype)
            context._add_new_cell(my_cell)
            self.connect(my_cell)
        elif l == 1:
            my_cell = context._childids[self._cell_ids[0]]
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
    def __init__(self, process, identifier, dtype):
        OutputPinBase.__init__(self, process)
        self.solid = OutputPin(process, identifier, dtype)
        self.liquid = OutputPin(process, identifier, dtype)
        self.own(self.solid)
        self.own(self.liquid)

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
        self._pin._set_context(context, force_detach)

    @property
    def context(self):
        return self._pin.context

    def _get_manager(self):
        return self._pin._get_manager()

    def own(self, obj):
        return self._pin.own()

    def destroy(self):
        self._pin.destroy()

class ExportedOutputPin(ExportedPinBase, OutputPinBase):
    @property
    def _cell_ids(self):
        return self._pin._cell_ids

class ExportedInputPin(ExportedPinBase, InputPinBase):
    pass

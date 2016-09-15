#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary

from . import logger
from .exceptions import InvalidContextException


class Manager:

    def __init__(self):
        self.listeners = {}
        self.pin_to_cells = {}
        self.cells = WeakValueDictionary()

    def add_listener(self, cell, input_pin):
        cell_id = self.get_cell_id(cell)
        pin_ref = weakref.ref(input_pin)

        try:
            listeners = self.listeners[cell_id]
            assert input_pin not in listeners
            # TODO: tolerate (silently ignore) a connection that exists already?
            listeners.append(pin_ref)

        except KeyError:
            self.listeners[cell_id] = [pin_ref]

        try:
            curr_pin_to_cells = self.pin_to_cells[id(input_pin)]
            assert cell_id not in curr_pin_to_cells
            # TODO: tolerate (append) multiple inputs?
            curr_pin_to_cells.append(cell_id)

        except KeyError:
            self.pin_to_cells[id(input_pin)] = [cell_id]

    def remove_listener(self, input_pin):
        cell_ids = self.pin_to_cells.pop(id(input_pin), [])
        for cell_id in cell_ids:
            l = self.listeners[cell_id]
            l[:] = [ref for ref in l if id(ref()) != id(input_pin)]
            if not len(l):
                self.listeners.pop(cell_id)

    def _update(self, cell_id, value):
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
            logger.warn("Unable to update cell '{}' , cell has died".format(cell_id))
            return

        changed = cell._update(value)

        if changed:
            self._update(cell_id, value)

    @classmethod
    def get_cell_id(cls, cell):
        return id(cell)

    def connect(self, source, target):
        from .cell import Cell

        if isinstance(source, Cell):
            assert isinstance(target, InputPin)
            assert source._context is not None and source._context._manager is self
            assert target._context is not None and target._context._manager is self

            process = target.process_ref()
            assert process is not None # weakref may not be dead

            source._on_connect(target, process, incoming=False)
            self.add_listener(source, target)

            if source.status == Cell.StatusFlags.OK:
                self.update_from_code(source)

        elif isinstance(source, OutputPin):
            assert isinstance(target, Cell)
            process = source.process_ref()
            assert process is not None #weakref may not be dead
            target._on_connect(source, process, incoming=True)

            cell_id = self.get_cell_id(target)
            if cell_id not in self.cells:
                self.cells[cell_id] = target

            if cell_id not in source._cell_ids:
                source._cell_ids.append(cell_id)


class Managed:
    _context = None

    def set_context(self, context):
        assert isinstance(context, Context)
        self._context = context
        return self

    def get_context(self):
        if self._context is None:
            raise InvalidContextException("No valid context exists to perform required operation")

        return self._context

    def get_manager(self):
        context = self.get_context()
        return context._manager


class Process(Managed):
    """Base class for all processes."""

    def __init__(self, params):
        self._pins = {}
        self.output_names = set()

        for param_name in params:
            param = params[param_name]

            if param["pin"] == "input":
                pin = self._create_input_pin(param_name, param["dtype"])

            else:
                assert param["pin"] == "output"
                pin = self._create_output_pin(param_name, param["dtype"])
                self.output_names.add(param_name)

            self._pins[param_name] = pin

    def __del__(self):
        try:
            self.destroy()

        except:
            logger.exception('Error calling Process.destroy()')

    def __getattr__(self, name):
        try:
            return self._name_to_pin[name]

        except KeyError:
            raise AttributeError(name)

    def destroy(self):
        self.__dict__.update({n: None for n in self._pins})

    def set_context(self, context):
        super(Process, self).set_context(context)

        for pin in self._pins.values():
            pin.set_context(context)

        return self

    def _create_input_pin(self, name, dtype):
        return InputPin(self, name, dtype)

    def _create_output_pin(self, name, dtype):
        return OutputPin(self, name, dtype)


class InputPin(Managed):

    def __init__(self, process, identifier, dtype):
        self.process_ref = weakref.ref(process)
        self.identifier = identifier
        self.dtype = dtype

    def cell(self):
        manager = self.get_manager()
        context = self.get_context()
        curr_pin_to_cells = manager.pin_to_cells.get(id(self), [])
        number_connected_cells = len(curr_pin_to_cells)

        if number_connected_cells == 1:
            cell = context.root()._childids[curr_pin_to_cells[0]]

        elif number_connected_cells == 0:
            if self.dtype is None:
                raise ValueError("Cannot construct cell() for pin with dtype=None")

            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")

            cell = context.root().cells.define(self.dtype)
            cell.connect(self)

        elif number_connected_cells > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")

        return cell

    def update(self, value):
        process = self.process_ref()
        if process is None:
            logger.warn("Unable to update input pin, process has died")
            return

        process.receive_update(self.identifier, value)

    def __del__(self):
        try:
            manager = self.get_manager()
            manager.remove_listener(self)

        except:
            logger.exception("Error in destruction of InputPin")


class OutputPin(Managed):

    def __init__(self, process, identifier, dtype):
        self.process_ref = weakref.ref(process)
        self.identifier = identifier
        self.dtype = dtype
        self._cell_ids = []

    def update(self, value):
        manager = self.get_manager()
        for cell_id in self._cell_ids:
            manager.update_from_process(cell_id, value)

    def connect(self, target):
        manager = self.get_manager()
        manager.connect(self, target)

    def cell(self):
        context = self.get_context()
        number_connected_cells = len(self._cell_ids)

        if number_connected_cells == 0:
            if self.dtype is None:
                raise ValueError("Cannot construct cell() for pin with dtype=None")

            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")

            cell = context.root().cells.define(self.dtype)
            self.connect(cell)

        elif number_connected_cells == 1:
            cell = context.root()._childids[self._cell_ids[0]]

        elif number_connected_cells > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")

        return cell

    def cells(self):
        context = self.get_context()
        cells = [c for c in (context.cells[c] for c in self._cell_ids) if c is not None]
        return cells


class EditorOutputPin(Managed):

    def __init__(self, process, identifier, dtype):
        self.solid = OutputPin(process, identifier, dtype)
        self.liquid = OutputPin(process, identifier, dtype)

    def update(self, value):
        self.solid.update(value)
        self.liquid.update(value)

    def connect(self, target):
        raise TypeError("Cannot connect EditorOutputPin, select .solid or .liquid")

    def cell(self):
        raise TypeError("Cannot obtain .cell for EditorOutputPin, select .solid or .liquid")

    def cells(self):
        raise TypeError("Cannot obtain .cells for EditorOutputPin, select .solid or .liquid")

    def set_context(self, context):
        Managed.set_context(self, context)
        self.solid.set_context(context)
        self.liquid.set_context(context)


from .context import Context

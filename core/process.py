#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary

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
            return #cell has died...

        cell._update(value)
        self._update(cell_id, value)

    @classmethod
    def get_cell_id(cls, cell):
        return id(cell)

    def connect(self, source, target):
        from .cell import Cell
        if isinstance(source, Cell):
            assert isinstance(target, InputPin)
            assert source._context is not None and \
                source._context._manager is self
            assert target._context is not None and \
                target._context._manager is self

            process = target.process_ref()
            assert process is not None #weakref may not be dead
            source._on_connect(target, process, incoming = False)
            self.add_listener(source, target)

            if source._status == Cell.StatusFlags.OK:
                self.update_from_code(source)

        elif isinstance(source, OutputPin):
            assert isinstance(target, Cell)
            process = source.process_ref()
            assert process is not None #weakref may not be dead
            target._on_connect(source, process, incoming = True)
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

    def _get_context(self):
        if self._context is None:
            raise Exception(
             "Cannot carry out requested operation without a context"
            )
        return self._context

    def _get_manager(self):
        context = self._get_context()
        return context._manager

class Process(Managed):
    """Base class for all processes."""
    pass

class InputPin(Managed):

    def __init__(self, process, identifier, dtype):
        self.process_ref = weakref.ref(process)
        self.identifier = identifier
        self.dtype = dtype

    def cell(self):
        manager = self._get_manager()
        context = self._get_context()
        curr_pin_to_cells = manager.pin_to_cells.get(id(self), [])
        l = len(curr_pin_to_cells)
        if l == 0:
            if self.dtype is None:
                raise ValueError(
                 "Cannot construct cell() for pin with dtype=None"
                )
            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")
            cell = context.root().cells.define(self.dtype)
            cell.connect(self)
        elif l == 1:
            cell = context.cells[curr_pin_to_cells[0]]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        return cell


    def update(self, value):
        process = self.process_ref()
        if process is None:
            return #Process has died...

        process.receive_update(self.identifier, value)

    def __del__(self):
        try:
            manager = self._get_manager()
            manager.remove_listener(self)
        except:
            pass


class OutputPin(Managed):
    def __init__(self, process, identifier, dtype):
        self.process_ref = weakref.ref(process)
        self.identifier = identifier
        self.dtype = dtype
        self._cell_ids = []

    def update(self, value):
        manager = self._get_manager()
        for cell_id in self._cell_ids:
            manager.update_from_process(cell_id, value)

    def connect(self, target):
        manager = self._get_manager()
        manager.connect(self, target)

    def cell(self):
        context = self._get_context()
        l = len(self._cell_ids)
        if l == 0:
            if self.dtype is None:
                raise ValueError(
                 "Cannot construct cell() for pin with dtype=None"
                )
            process = self.process_ref()
            if process is None:
                raise ValueError("Process has died")
            cell = context.root().cells.define(self.dtype)
            self.connect(cell)
        elif l == 1:
            context = self._get_context()
            cell = context.cells[self._cell_ids[0]]
        elif l > 1:
            raise TypeError("cell() is ambiguous, multiple cells are connected")
        return cell

    def cells(self):
        context = self._get_context()
        cells = [context.cells[c] for c in self._cell_ids]
        cells = [c for c in cells if c is not None]
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

from .context import Context

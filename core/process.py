#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary

class Process:
    """Base class for all processes."""
    pass

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
            pin_to_cells = self.pin_to_cells[id(input_pin)]
            assert cell_id not in pin_to_cells
            # TODO: tolerate (append) multiple inputs?
            pin_to_cells.append(cell_id)

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

    def update_from_controller(self, cell_id, value):
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
            controller = target.controller_ref()
            assert controller is not None #weakref may not be dead
            source._on_connect(target, controller, incoming = False)
            self.add_listener(source, target)

            if source._status == Cell.StatusFlags.OK:
                self.update_from_code(source)

        elif isinstance(source, OutputPin):
            assert isinstance(target, Cell)
            controller = source.controller_ref()
            assert controller is not None #weakref may not be dead
            target._on_connect(source, controller, incoming = True)
            cell_id = self.get_cell_id(target)
            if cell_id not in self.cells:
                self.cells[cell_id] = target

            assert source.cell_id is None #TODO: support multiple connections
            source.cell_id = cell_id

manager = Manager()


#TODO: declare types!
class InputPin:

    def __init__(self, controller, identifier):
        self.controller_ref = weakref.ref(controller)
        self.identifier = identifier

    def update(self, value):
        controller = self.controller_ref()
        if controller is None:
            return #Process has died...

        controller.receive_update(self.identifier, value)

    def __del__(self):
        try:
            manager.remove_listener(self)

        except:
            pass


class OutputPin:
    _cell_id = None

    def __init__(self, controller, identifier):
        self.controller_ref = weakref.ref(controller)
        self.identifier = identifier

    @property
    def cell_id(self):
        return self._cell_id

    @cell_id.setter
    def cell_id(self, value):
        self._cell_id = value

    def update(self, value):
        manager.update_from_controller(self._cell_id, value)

    def connect(self, target):
        manager.connect(self, target)


def connect(source, target):
    manager.connect(source, target)

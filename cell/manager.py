#stub, TODO: refactor, document
import weakref
from weakref import WeakValueDictionary, WeakKeyDictionary

class Manager:
    def __init__(self):
        self.listeners = {}
        self.rev_listeners = {}
        self.cells = WeakValueDictionary()

    def add_listener(self, cell, inputpin):
        cellid = self.get_cellid(cell)
        ipref = weakref.ref(inputpin)
        try:
            listeners = self.listeners[cellid]
            assert inputpin not in listeners
            #TODO: tolerate (silently ignore) a connection that exists already?
            listeners.append(ipref)
        except KeyError:
             self.listeners[cellid] = [ipref]
        try:
            rev_listeners = self.rev_listeners[id(inputpin)]
            assert cellid not in rev_listeners
            #TODO: tolerate (append) multiple inputs?
            rev_listeners.append(cellid)
        except KeyError:
            self.rev_listeners[id(inputpin)] = [cellid]

    def remove_listener(self, inputpin):
        cellids = self.rev_listeners.pop(id(inputpin), [])
        for cellid in cellids:
            l = self.listeners[cellid]
            l[:] = [ref for ref in l if id(ref()) != id(inputpin) ]
            if not len(l):
                self.listeners.pop(cellid)

    def _update(self, cellid, value):
        listeners = self.listeners.get(cellid, [])
        for inputpin_ref in listeners:
            inputpin = inputpin_ref()
            if inputpin is None: continue #TODO: error?
            inputpin.update(value)

    def update_from_code(self, cell):
        value = cell._data
        cellid = self.get_cellid(cell)
        self._update(cellid, value)

    def update_from_controller(self, cellid, value):
        cell = self.cells.get(cellid, None)
        if cell is None:
            return #cell has died...
        cell._update(value)
        self._update(cellid, value)

    @classmethod
    def get_cellid(cls, cell):
        return id(cell)

    def connect(self, source, target):
        from .Cell import Cell
        if isinstance(source, Cell):
            assert isinstance(target, InputPin)
            self.add_listener(source, target)
            controller = target.controller()
            assert controller is not None #weakref may not be dead
            source._on_connect(controller)
            if source.status == "OK":
                self.update_from_code(source)
        elif isinstance(source, OutputPin):
            assert isinstance(target, Cell)
            cellid = self.get_cellid(target)
            if cellid not in self.cells:
                self.cells[cellid] = target
            assert source.cellid is None #TODO: support multiple connections
            source.cellid = cellid

manager = Manager()

#TODO: declare types!
class InputPin:
    def __init__(self, controller, identifier):
        self.controller = weakref.ref(controller)
        self.identifier = identifier
    def update(self, value):
        controller = self.controller()
        if controller is None: return #Process has died...
        controller.receive_update(self.identifier, value)
    def __del__(self):
        try:
            manager.remove_listener(self)
        except:
            pass

class OutputPin:
    _cellid = None
    @property
    def cellid(self):
        return self._cellid
    @cellid.setter
    def cellid(self, value):
        self._cellid = value
    def update(self, value):
        manager.update_from_controller(self._cellid, value)
    def connect(self, target):
        manager.connect(self, target)

def connect(source, target):
    manager.connect(source, target)

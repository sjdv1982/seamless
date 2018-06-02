"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

The manager has a notion of the managers of the subcontexts
manager.set_cell and manager.pin_send_update are thread-safe (can be invoked from any thread)
TODO: The manager can maintain a value dict and an exception dict (in text/cell form; the cells themselves hold the Python objects)

TODO: once reactors arrive (or any kind of sync evaluation), keep a stack of cells that have been updated since the current sync action
 this to break a single unresponsive endless feedback cycle into lots of cycles with one-update-per-cycle
"""

import threading
import functools

class Manager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sub_managers = {}
        self.cell_to_pins = {} #cell => inputpins
        self.cell_to_cells = {} #cell => (index, alias target cell, alias mode) list
        self.cell_from_pin = {} #cell => outputpin
        self.cell_from_cell = {} #alias target cell => (index, source cell, alias mode)
        self.pin_from_cell = {} #inputpin => (index, cell)
        self.pin_to_cells = {} #outputpin => (index, cell) list
        self._ids = 0
        self.unstable = set()
        #for now, just a single global workqueue
        from .mainloop import workqueue
        self.workqueue = workqueue
        #for now, just a single global mountmanager
        from .mount import mountmanager
        self.mountmanager = mountmanager

    def set_stable(self, worker, value):
        if value:
            self.unstable.remove(worker)
        else:
            self.unstable.add(worker)

    def get_id(self):
        self._ids += 1
        return self._ids

    def _update_cell_from_cell(self, cell, target, alias_mode):
        #TODO: negotiate proper serialization protocol (see cell.py, end of file)
        assert cell._get_manager() is self
        mode, submode = alias_mode, None
        value = cell.serialize(mode, submode)
        different = target.deserialize(value, mode, submode,
          #from_pin is set to True, also for aliases...
          from_pin=True, default=False, cosmetic=False
        )
        other = target._get_manager()
        if target._mount is not None:
            other.mountmanager.add_cell_update(target)
        if different:
            other.cell_send_update(target)

    def _connect_cell_to_cell(self, cell, target, alias_mode):

        if not target.authoritative:
            raise Exception("%s: is non-authoritative (already dependent on another worker/cell)" % target)
        other = target._get_manager()

        con_id = self.get_id()
        connection = (con_id, target, alias_mode)
        rev_connection = (con_id, cell, alias_mode)

        if cell not in self.cell_to_cells:
            self.cell_to_cells[cell] = []
        self.cell_to_cells[cell].append(connection)
        other.cell_from_cell[target] = rev_connection
        target._authoritative = False

        if cell._status == Cell.StatusFlags.OK:
            self._update_cell_from_cell(cell, target, alias_mode)


    def connect_cell(self, cell, target, alias_mode=None):
        if alias_mode is None:
            alias_mode = "copy" ###
        assert isinstance(cell, CellLikeBase)
        assert not isinstance(cell, Inchannel)
        assert cell._get_manager() is self
        other = target._get_manager()
        assert isinstance(target, (InputPinBase, EditPinBase, CellLikeBase))
        if isinstance(target, ExportedInputPin):
            target = target.get_pin()

        if isinstance(target, CellLikeBase):
            assert not isinstance(target, Outchannel)
            return self._connect_cell_to_cell(cell, target, alias_mode)

        worker = target.worker_ref()
        assert worker is not None #weakref may not be dead
        cell._check_mode(target.mode, target.submode)
        con_id = self.get_id()

        connection = (con_id, target)
        rev_connection = (con_id, cell)

        if cell._status == Cell.StatusFlags.OK:
            value = cell.serialize(target.mode, target.submode)
            target.receive_update(value)
        else:
            if isinstance(target, EditPinBase) and target.last_value is not None:
                raise NotImplementedError ### also output *to* the cell!
                """
                self.update_from_worker(
                    self.get_cell_id(source),
                    target.last_value,
                    worker, preliminary=False
                )
                """

        if isinstance(target, EditPinBase):
            raise NotImplementedError ### also output *to* the cell!

        if cell not in self.cell_to_pins:
            self.cell_to_pins[cell] = []
        self.cell_to_pins[cell].append(connection)
        other.pin_from_cell[target] = rev_connection

    def connect_pin(self, pin, target):
        assert pin._get_manager() is self
        other = target._get_manager()
        assert isinstance(target, CellLikeBase)
        if isinstance(pin, ExportedOutputPin):
            pin = pin.get_pin()
        if isinstance(pin, EditPinBase):
            raise NotImplementedError ### also output *from* the cell!
        assert isinstance(pin, OutputPinBase)
        worker = pin.worker_ref()
        assert worker is not None #weakref may not be dead

        if not target.authoritative:
            raise Exception("%s: is non-authoritative (already dependent on another worker/cell)" % target)

        target._check_mode(pin.mode, pin.submode)
        con_id = self.get_id()
        connection = (con_id, target)
        rev_connection = (con_id, pin)

        if pin not in self.pin_to_cells:
            self.pin_to_cells[pin] = []
        self.pin_to_cells[pin].append(connection)
        other.cell_from_pin[target] = rev_connection
        target._authoritative = False

        if isinstance(worker, Transformer):
            worker._on_connect_output()
            if worker._last_value is not None:
                raise NotImplementedError
        elif pin.last_value is not None:
            raise NotImplementedError #previously unconnected reactor output
            """
            self.update_from_worker(
                cell_id,
                source.last_value,
                worker,
                preliminary=False
            )
            """

    def set_cell(self, cell, value, *,
      default=False, cosmetic=False, from_buffer=False, force=False
    ):
        assert isinstance(cell, CellLikeBase)
        assert cell._get_manager() is self
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(
              self.set_cell, cell, value,
              default=default, cosmetic=cosmetic, from_buffer=from_buffer,
              force=force
            )
            self.workqueue.append(work)
            return
        mode = "buffer" if from_buffer else "ref"
        different = cell.deserialize(value, mode, None,
          from_pin=False, default=default, cosmetic=cosmetic,force=force
        )
        if not cosmetic:
            for con_id, pin in self.cell_to_pins.get(cell, []):
                value = cell.serialize(pin.mode, pin.submode)
                pin.receive_update(value)
        if cell._mount is not None:
            self.mountmanager.add_cell_update(cell)
        if different:
            self.cell_send_update(cell)

    def notify_attach_child(self, childname, child):
        if isinstance(child, Context):
            assert isinstance(child._manager, Manager)
            self.sub_managers[childname] = child._manager
        elif isinstance(child, Cell):
            if child._prelim_val is not None:
                value, default = child._prelim_val
                self.set_cell(child, value, default=default, cosmetic=False)
                child._prelim_val = None
        elif isinstance(child, Worker):
            child.activate()
        #then, trigger hook (not implemented) #TODO

    def pin_send_update(self, pin, value, preliminary):
        #TODO: explicit support for preliminary values
        #TODO: edit pins => from_pin = "edit"
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(
              self.pin_send_update, pin, value, preliminary
            )
            self.workqueue.append(work)
            return
        for con_id, cell in self.pin_to_cells.get(pin,[]):
            different = cell.deserialize(value, pin.mode, pin.submode,
              from_pin=True, default=False, cosmetic=False
            )
            other = cell._get_manager()
            if cell._mount is not None:
                other.mountmanager.add_cell_update(cell)
            if different:
                other.cell_send_update(cell)

    def cell_send_update(self, cell):
        #Activates aliases
        assert threading.current_thread() == threading.main_thread()
        assert isinstance(cell, CellLikeBase)
        for con_id, target, alias_mode in self.cell_to_cells.get(cell, []):
            #from_pin is set to True, also for aliases
            self._update_cell_from_cell(cell, target, alias_mode)



from .context import Context
from .cell import Cell, CellLikeBase
from .worker import Worker, InputPin, EditPin, InputPinBase, EditPinBase, \
 OutputPinBase, ExportedInputPin, ExportedOutputPin
from .transformer import Transformer
from .structured_cell import Inchannel, Outchannel

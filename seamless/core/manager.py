"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

The manager has a notion of the managers of the subcontexts
manager.set_cell and manager.pin_send_update are thread-safe (can be invoked from any thread)
TODO: The manager can maintain a value dict and an exception dict (in text/cell form; the cells themselves hold the Python objects)
"""

import threading
import functools

class Manager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sub_managers = {}
        self.cell_to_pins = {} #cell => inputpins
        self.cell_from_pin = {} #cell => outputpin
        self.pin_from_cell = {} #inputpin => cell
        self.pin_to_cells = {} #outputpin => cells
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

    def connect_cell(self, cell, target):
        assert isinstance(target, (InputPinBase, EditPinBase, Cell))
        if isinstance(target, ExportedInputPin):
            target = target.get_pin()

        if isinstance(target, Cell):
            raise NotImplementedError
            """
            self.add_cell_alias(source, target)
            target._on_connect(source, None, incoming = True)
            if source._status == Cell.StatusFlags.OK:
                value = source._data
                if source.dtype is not None and \
                  (source.dtype == "cson" or source.dtype[0] == "cson") and \
                  target.dtype is not None and \
                  (target.dtype == "json" or target.dtype[0] == "json"):
                    if isinstance(value, (str, bytes)):
                        value = cson2json(value)
                target._update(value,propagate=True)
            """
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
        self.pin_from_cell[target] = rev_connection

    def connect_pin(self, pin, target):
        assert isinstance(target, Cell)
        if isinstance(pin, ExportedOutputPin):
            pin = pin.get_pin()
        worker = pin.worker_ref()
        assert worker is not None #weakref may not be dead
        if isinstance(pin, EditPinBase):
            raise NotImplementedError ### also output *from* the cell!
        assert isinstance(pin, OutputPinBase)

        if not target.authoritative:
            raise Exception("%s: is non-authoritative (already dependent on another worker)" % target)

        target._check_mode(pin.mode, pin.submode)
        con_id = self.get_id()
        connection = (con_id, target)
        rev_connection = (con_id, pin)

        if pin not in self.pin_to_cells:
            self.pin_to_cells[pin] = []
        self.pin_to_cells[pin].append(connection)
        self.cell_from_pin[target] = connection
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
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(
              self.set_cell, cell, value,
              default=default, cosmetic=cosmetic, from_buffer=from_buffer,
              force=force
            )
            self.workqueue.append(work)
            return
        mode = "buffer" if from_buffer else "ref"
        cell.deserialize(value, mode, None,
          from_pin=False, default=default, cosmetic=cosmetic,force=force
        )
        if cell._mount is not None:
            self.mountmanager.add_cell_update(cell)
        if not cosmetic:
            for con_id, pin in self.cell_to_pins.get(cell, []):
                value = cell.serialize(pin.mode, pin.submode)
                pin.receive_update(value)

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
        if pin in self.pin_to_cells:
            for con_id, cell in self.pin_to_cells[pin]:
                cell.deserialize(value, pin.mode, pin.submode,
                  from_pin=True, default=False, cosmetic=False
                )
                if cell._mount is not None:
                    self.mountmanager.add_cell_update(cell)



from .context import Context
from .cell import Cell, CellLikeBase
from .worker import Worker, InputPin, EditPin, InputPinBase, EditPinBase, \
 OutputPinBase, ExportedInputPin, ExportedOutputPin
from .transformer import Transformer
from .structured_cell import MixedOutchannel

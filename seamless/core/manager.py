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
import weakref

def main_thread_buffered(func):
    def main_thread_buffered_wrapper(self, *args, **kwargs):
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(func, self, *args, **kwargs)
            self.workqueue.append(work)
        else:
            func(self, *args, **kwargs)
    return main_thread_buffered_wrapper

def manager_buffered(func):
    def manager_buffered_wrapper(self, *args, **kwargs):
        if not self.active and not self.flushing:
            work = functools.partial(func, self, *args, **kwargs)
            self.buffered_work.append(work)
        else:
            func(self, *args, **kwargs)
    return manager_buffered_wrapper

def with_successor(argname, argindex):
    def with_successor_outer_wrapper(func):
        def with_successor_wrapper(self, *args0, **kwargs0):
            args, kwargs = args0, kwargs0
            if self.destroyed and self.successor:
                raise NotImplementedError #untested! need to implement destroyed, successor
                if len(args) > argindex:
                    target = args[argindex]
                elif target in kwargs:
                    target = kwargs[argname]
                else:
                    raise TypeError((argname, argindex))

                if isinstance(target, CellLikeBase):
                    successor_target = getattr(self.successor, target.name)
                elif isinstance(target, InputPin):
                    worker_name = target.get_workerr().name #pin.get_worker()? can't remember API
                    successor_target = attr(self.successor, worker_name).pinsss[target.name] ##pins[]? can't remember API

                if successor_target._manager.destroyed:
                    return
                if len(args) > argindex:
                    args = args[:argindex] + [successor_target] + args[argindex+1:]
                elif target in kwargs:
                    kwargs = kwargs.copy()
                    kwargs[argname] = successor_target
            return func(self, *args, **kwargs)
        return with_successor_wrapper
    return with_successor_outer_wrapper

class Manager:
    active = True
    destroyed = False
    successor = None
    flushing = False
    def __init__(self, ctx):
        self.ctx = weakref.proxy(ctx)
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
        self.buffered_work = []

    @main_thread_buffered
    @manager_buffered
    def set_stable(self, worker, value):
        if self.destroyed:
            return
        if value:
            self.unstable.remove(worker)
        else:
            self.unstable.add(worker)

    def activate(self):
        self.active = True
        for childname, child in self.ctx._children.items():
            if isinstance(child, Context):
                child._manager.activate()
        self.flush()

    def deactivate(self):
        self.active = False
        for childname, child in self.ctx._children.items():
            if isinstance(child, Context):
                child._manager.deactivate()


    def stop_flushing(self):
        self.flushing = False
        for childname, child in self.ctx._children.items():
            if isinstance(child, Context):
                child._manager.stop_flushing()

    def flush(self, from_parent=False):
        assert threading.current_thread() == threading.main_thread()
        assert self.active or self.destroyed
        self.flushing = True
        for childname, child in self.ctx._children.items():
            if isinstance(child, Context):
                child._manager.flush(from_parent=True) # need to flush only once
                                            # with self.active or self.destroyed, work buffer shouldn't accumulate
        try:
            self.workqueue.flush()
            while self.active and len(self.buffered_work):
                item = self.buffered_work.pop(0)
                try:
                    item()
                except:
                    traceback.print_exc()
                    #TODO: log exception
        finally:
            if not from_parent:
                self.stop_flushing()

    def destroy(self):
        self.destroyed = True
        for childname, child in self.ctx._children.items():
            if isinstance(child, Context):
                child.destroy(cells=False)
        #all of the children are now dead
        #  only in the buffered_work and the work queue there is still some function calls to the children

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

    @main_thread_buffered
    @manager_buffered
    def connect_cell(self, cell, target, alias_mode=None):
        if self.destroyed:
            return
        if alias_mode is None:
            alias_mode = "copy" ###
        assert isinstance(cell, CellLikeBase)
        assert not isinstance(cell, Inchannel)
        assert cell._get_manager() is self
        other = target._get_manager()
        assert isinstance(target, (InputPinBase, EditPinBase, CellLikeBase))
        ###if isinstance(target, ExportedInputPin):
        ###    target = target.get_pin()

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

    @main_thread_buffered
    @manager_buffered
    def connect_pin(self, pin, target):
        if self.destroyed:
            return
        assert pin._get_manager() is self
        other = target._get_manager()
        assert isinstance(target, CellLikeBase)
        ###if isinstance(pin, ExportedOutputPin):
        ###    pin = pin.get_pin()
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

    @main_thread_buffered
    @manager_buffered
    @with_successor("cell", 0)
    def set_cell(self, cell, value, *,
      default=False, cosmetic=False, from_buffer=False, force=False
    ):
        if self.destroyed:
            return
        assert isinstance(cell, CellLikeBase)
        assert cell._get_manager() is self
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

    @main_thread_buffered
    @manager_buffered
    @with_successor("cell", 0)
    def touch_cell(self, cell):
        if self.destroyed:
            return
        assert isinstance(cell, CellLikeBase)
        assert cell._get_manager() is self
        for con_id, pin in self.cell_to_pins.get(cell, []):
            value = cell.serialize(pin.mode, pin.submode)
            pin.receive_update(value)
        self.cell_send_update(cell)
        if cell._mount is not None:
            self.mountmanager.add_cell_update(cell)

    @main_thread_buffered
    @manager_buffered
    @with_successor("worker", 0)
    def touch_worker(self, worker):
        if self.destroyed:
            return
        assert isinstance(worker, Worker)
        assert worker._get_manager() is self
        worker._touch()

    @main_thread_buffered
    @manager_buffered
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

    @main_thread_buffered
    @manager_buffered
    @with_successor("pin", 0)
    def pin_send_update(self, pin, value, preliminary):
        #TODO: explicit support for preliminary values
        #TODO: edit pins => from_pin = "edit"
        for con_id, cell in self.pin_to_cells.get(pin,[]):
            other = cell._get_manager()
            if other.destroyed:
                continue
            different = cell.deserialize(value, pin.mode, pin.submode,
              from_pin=True, default=False, cosmetic=False
            )
            if cell._mount is not None:
                other.mountmanager.add_cell_update(cell)
            if different:
                other.cell_send_update(cell)

    @main_thread_buffered
    @manager_buffered
    @with_successor("cell", 0)
    def cell_send_update(self, cell):
        if self.destroyed:
            return
        #Activates aliases
        assert isinstance(cell, CellLikeBase)
        for con_id, target, alias_mode in self.cell_to_cells.get(cell, []):
            #from_pin is set to True, also for aliases
            self._update_cell_from_cell(cell, target, alias_mode)

    def destroy_cell(self, cell):
        assert isinstance(cell, CellLikeBase)
        assert cell._get_manager() is self
        if cell._mount is not None:
            self.mountmanager.unmount(cell._mount["path"])

from .context import Context
from .cell import Cell, CellLikeBase
from .worker import Worker, InputPin, EditPin, InputPinBase, EditPinBase, \
 OutputPinBase#, ExportedInputPin, ExportedOutputPin
from .transformer import Transformer
from .structured_cell import Inchannel, Outchannel

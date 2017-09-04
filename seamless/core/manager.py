import json
from ..dtypes.cson import cson2json
import weakref
from weakref import WeakKeyDictionary, WeakValueDictionary, WeakSet
from ..dtypes import TransportedArray

#TODO: disconnect method (see MacroObject for low-level implementation)

def head(value):
    return str(value)[:50].replace("\n","\\n")

class Manager:

    def __init__(self):
        self.listeners = {}
        self.cell_aliases = {}
        self.cell_rev_aliases = {}
        self.macro_listeners = {}
        self.observers = {}
        self.registrar_listeners = WeakKeyDictionary()
        self.rev_registrar_listeners = WeakKeyDictionary()
        self.pin_to_cells = {}
        self.cells = WeakValueDictionary()
        self.cell_to_output_pin = WeakKeyDictionary()
        self._childids = WeakValueDictionary()
        self.registrar_items = []
        self.unstable_workers = WeakSet()
        super().__init__()

    def set_stable(self, worker, value):
        assert value in (True, False), value
        if not value:
            #print("UNSTABLE", worker)
            self.unstable_workers.add(worker)
        else:
            #print("STABLE", worker)
            self.unstable_workers.discard(worker)

    def add_cell_alias(self, source, target):
        from .cell import Cell
        assert isinstance(source, Cell)
        assert isinstance(target, Cell)
        assert source is not target
        cell_id = self.get_cell_id(source)
        target_ref = weakref.ref(target)

        try:
            aliases = self.cell_aliases[cell_id]
            if target_ref not in aliases:
                aliases.append(target_ref)

        except KeyError:
            self.cell_aliases[cell_id] = [target_ref]

        if cell_id not in self.cells:
            self.cells[cell_id] = source

        #reverse alias
        cell_id = self.get_cell_id(target)
        source_ref = weakref.ref(source)

        try:
            rev_aliases = self.cell_rev_aliases[cell_id]
            if source_ref not in rev_aliases:
                rev_aliases.append(source_ref)

        except KeyError:
            self.cell_rev_aliases[cell_id] = [source_ref]

        if cell_id not in self.cells:
            self.cells[cell_id] = target

    def add_registrar_item(self, registrar_name, dtype, data, data_name):
        item = registrar_name, dtype, data, data_name
        for curr_item in self.registrar_items:
            if data_name is None:
                exists = (curr_item[:3] == item[:3])
            else:
                exists = (curr_item[:2] == item[:2]) and \
                  curr_item[3] == data_name
            if exists:
                raise ValueError("Registrar item already exists")
        self.registrar_items.append(item)

    def remove_registrar_item(self, registrar_name, dtype, data, data_name):
        item = registrar_name, dtype, data, data_name
        self.registrar_items.remove(item)

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

    def _remove_listener(self, cell_id, input_pin, worker):
        input_pin_id = input_pin.get_pin_id()
        l = self.listeners[cell_id]
        l[:] = [ref for ref in l if ref().get_pin_id() != input_pin_id]
        if not len(l):
            self.listeners.pop(cell_id)
            cell = self.cells.get(cell_id, None)
            if cell is not None:
                cell._on_disconnect(input_pin, worker, False)

    def remove_listener(self, cell, input_pin):
        worker = input_pin.worker_ref()
        input_pin_id = input_pin.get_pin_id()
        cell_ids = self.pin_to_cells.pop(input_pin_id, [])
        cell_id = self.get_cell_id(cell)
        self._remove_listener(cell_id, input_pin, worker)

    def remove_listeners_pin(self, input_pin):
        worker = input_pin.worker_ref()
        cell_ids = self.pin_to_cells.pop(input_pin.get_pin_id(), [])
        for cell_id in cell_ids:
            self._remove_listener(cell_id, input_pin, worker)

    def remove_aliases(self, cell):
        cell_id = self.get_cell_id(cell)
        cell_ref = weakref.ref(cell)
        targets = self.cell_aliases.pop(cell_id, [])

        for target_ref in targets:
            target = target_ref()
            if target is None:
                continue
            target._on_disconnect(cell, None, incoming=True)
            target_id = self.get_cell_id(target)
            r = self.cell_rev_aliases[target_id]
            r[:] = [rr for rr in r if rr is not cell_ref]
            if not len(r):
                self.cell_rev_aliases.pop(target_id)

        #rev_aliases
        targets = self.cell_rev_aliases.pop(cell_id, [])

        for target_ref in targets:
            target = target_ref()
            if target is None:
                continue
            target_id = self.get_cell_id(target)
            r = self.cell_aliases[target_id]
            r[:] = [rr for rr in r if rr is not cell_ref]
            if not len(r):
                self.cell_aliases.pop(target_id)

    def remove_listeners_cell(self, cell):
        cell_id = self.get_cell_id(cell)
        listeners = self.listeners.pop(cell_id, [])
        for listener in listeners:
            pin = listener()
            if pin is None:
                continue
            pin_id = pin.get_pin_id()
            if pin_id not in self.pin_to_cells:
                continue
            self.pin_to_cells[pin_id][:] = \
                [c for c in self.pin_to_cells[pin_id] if c != cell_id ]


    def add_macro_listener(self, cell, macro_object, macro_arg):
        cell_id = self.get_cell_id(cell)
        m = (macro_object, macro_arg)

        try:
            macro_listeners = self.macro_listeners[cell_id]
            assert m not in macro_listeners
            macro_listeners.append(m)

        except KeyError:
            self.macro_listeners[cell_id] = [m]
            if cell_id not in self.cells:
                self.cells[cell_id] = cell

    def remove_macro_listener(self, cell, macro_object, macro_arg):
        cell_id = self.get_cell_id(cell)
        m = (macro_object, macro_arg)

        if cell_id in self.macro_listeners:
            l = self.macro_listeners[cell_id]
            if m in l:
                l.remove(m)

    def remove_macro_listeners_cell(self, cell):
        cell_id = self.get_cell_id(cell)
        listeners = self.macro_listeners.pop(cell_id, [])


    def add_registrar_listener(self, registrar, key, target, namespace_name):
        if registrar not in self.registrar_listeners:
            self.registrar_listeners[registrar] = {}
        d = self.registrar_listeners[registrar]
        if key not in d:
            d[key] = []
        d[key].append((weakref.ref(target), namespace_name))

        if target not in self.rev_registrar_listeners:
            self.rev_registrar_listeners[target] = {}
        r = self.rev_registrar_listeners[target]
        if key not in r:
            r[key] = []
        r[key].append(weakref.ref(registrar))

    def remove_registrar_listeners(self, target):
        if target not in self.rev_registrar_listeners:
            return
        rev = self.rev_registrar_listeners.pop(target)
        for key in rev:
            for registrar_ref in rev[key]:
                registrar = registrar_ref()
                if registrar not in self.registrar_listeners:
                    continue
                r = self.registrar_listeners[registrar]
                t = r[key]
                t[:] = [tt for tt in t if tt[0]() is not None and tt[0]() is not target]
                if not len(t):
                    r.pop(key)
                    if not len(r):
                        self.registrar_listeners.pop(registrar)


    def add_observer(self, cell, observer):
        cell_id = self.get_cell_id(cell)
        obs_ref = weakref.ref(observer)

        try:
            observers = self.observers[cell_id]
            assert obs_ref not in observers
            observers.append(obs_ref)
        except KeyError:
            self.observers[cell_id] = [obs_ref]
        if cell_id not in self.cells:
            self.cells[cell_id] = cell

    def remove_observer(self, cell, observer):
        cell_id = self.get_cell_id(cell)
        obs_ref = weakref.ref(observer)

        if cell_id in self.observers:
            l = self.observers[cell_id]
            if obs_ref in l:
                l.remove(obs_ref)

    def remove_observers_cell(self, cell):
        cell_id = self.get_cell_id(cell)
        listeners = self.observers.pop(cell_id, [])

    def _update(self, cell, dtype, value, *,
            worker=None, only_last=False):
        import threading
        assert threading.current_thread() is threading.main_thread()
        from .cell import Signal
        cell_id = self.get_cell_id(cell)

        observers = self.observers.get(cell_id, [])
        for observer in observers:
            obs = observer()
            if obs is not None:
                obs(value)

        macro_listeners = self.macro_listeners.get(cell_id, [])
        if not only_last:
            for macro_object, macro_arg in macro_listeners:
                try:
                    updated = macro_object.update_cell(macro_arg)
                except Exception:
                    #TODO: proper logging
                    import traceback
                    traceback.print_exc()

        aliases = self.cell_aliases.get(cell_id, [])
        for target_cell_ref in aliases:
            target_cell = target_cell_ref()
            if target_cell is not None:
                if isinstance(target_cell, Signal):
                    #print("cell-cell alias", cell, "=>", target_cell)
                    self._update(target_cell, None, None,
                        worker=worker, only_last=only_last)
                else:
                    value2 = value
                    if dtype is not None and \
                      (dtype == "cson" or dtype[0] == "cson") and \
                      target_cell.dtype is not None and \
                      (target_cell.dtype == "json" or target_cell.dtype[0] == "json"):
                        if isinstance(value, (str, bytes)):
                            value2 = cson2json(value)

                    target_cell._update(value2, propagate=True)

        listeners = self.listeners.get(cell_id, [])
        if only_last:
            listeners = listeners[-1:]

        resource_name0 = None
        if cell.resource is not None:
            resource_name0 = cell.resource.filepath
        for input_pin_ref in listeners:
            input_pin = input_pin_ref()

            if input_pin is None:
                continue #TODO: error?

            if worker is not None and input_pin.worker_ref() is worker:
                continue
            value2 = value
            if dtype is not None and \
              (dtype == "cson" or dtype[0] == "cson") and \
              input_pin.dtype is not None and \
              (input_pin.dtype == "json" or input_pin.dtype[0] == "json"):
                if isinstance(value, (str, bytes)):
                    value2 = cson2json(value)
            resource_name = "pin: " + input_pin.format_path()
            if resource_name0 is not None:
                resource_name = resource_name0 + " in " + resource_name
            try:
                input_pin.receive_update(value2, resource_name)
            except Exception:
                #TODO: proper logging
                import traceback
                traceback.print_exc()

    def update_from_code(self, cell, only_last=False):
        import seamless
        if cell.dtype == "array":
            value = TransportedArray(cell._data, cell._store)
        else:
            value = cell._data
        #print("manager.update_from_code", cell, head(value))
        self._update(cell, cell.dtype, value, only_last=only_last)
        from .. import run_work
        from .macro import get_macro_mode
        if not get_macro_mode():
            run_work()

    def update_from_worker(self, cell_id, value, worker, *, preliminary):
        import seamless
        from .cell import Signal
        cell = self.cells.get(cell_id, None)
        if cell is None or cell._destroyed:
            return #cell has died...
        #print("manager.update_from_worker", cell, head(value), worker)

        if isinstance(cell, Signal):
            assert value is None
            self._update(cell, None, None, worker=worker)
        else:
            changed = cell._update(value,propagate=False,
                preliminary=preliminary)
            if changed:
                if cell.dtype == "array":
                    value = TransportedArray(value, cell._store)
                self._update(cell, cell.dtype, value, worker=worker)

    def update_registrar_key(self, registrar, key):
        from .worker import Worker
        from .macro import MacroObject
        if registrar not in self.registrar_listeners:
            return
        d = self.registrar_listeners[registrar]
        if key not in d:
            return
        for t in list(d[key]):
            target = t[0]()
            if target is None:
                continue
            if isinstance(target, Worker):
                namespace_name = t[1]
                target.receive_registrar_update(registrar.name, key, namespace_name)
            elif isinstance(target, MacroObject):
                target.update_cell((registrar.name, key))
            else:
                raise TypeError(target)

    @classmethod
    def get_cell_id(cls, cell):
        return id(cell)

    def disconnect(self, source, target):
        from .transformer import Transformer
        from .cell import Cell, CellLike
        from .context import Context
        from .worker import EditPinBase, ExportedEditPin, \
            InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin
        if isinstance(source, EditPinBase):
            source, target = target, source
        if isinstance(source, CellLike) and source._like_cell:
            if isinstance(target, ExportedInputPin):
                target = target.get_pin()
            if isinstance(source, Context):
                assert "_output" in source._pins
                source = source._pins["_output"]
            self.remove_listener(source, target)
            worker = target.worker_ref()
            if worker is not None:
                source._on_disconnect(target, worker, incoming = False)

        elif isinstance(source, OutputPinBase):
            if isinstance(target, Context):
                assert "_input" in target._pins
                target = target._pins["_input"]
            if isinstance(source, ExportedOutputPin):
                source = source.get_pin()

            cell_id = self.get_cell_id(target)

            ok = False
            if cell_id in self.cells and \
              target in self.cell_to_output_pin:
                if cell_id not in source._cell_ids:
                    ok = False
                else:
                    for ref in self.cell_to_output_pin[target]:
                        if ref() is source:
                            self.cell_to_output_pin[target].remove(ref)
                            source._cell_ids.remove(cell_id)
                            ok = True
            if not ok:
                raise ValueError("Connection does not exist")

                if target not in self.cell_to_output_pin:
                    self.cell_to_output_pin[target] = []
                self.cell_to_output_pin[target].append(weakref.ref(source))

            worker = source.worker_ref()
            if worker is not None:
                if isinstance(worker, Transformer):
                    worker._on_disconnect_output()
                target._on_disconnect(source, worker, incoming = True)

        else:
            raise TypeError

    def connect(self, source, target):
        from .transformer import Transformer
        from .cell import Cell, CellLike
        from .context import Context
        from .worker import EditPinBase, ExportedEditPin, \
            InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin
        if isinstance(source, EditPinBase):
            source, target = target, source
        if isinstance(source, CellLike) and source._like_cell:
            assert isinstance(target, (InputPinBase, EditPinBase, CellLike))
            assert source._get_manager() is self
            assert target._get_manager() is self
            if isinstance(target, ExportedInputPin):
                target = target.get_pin()

            if isinstance(target, Cell):
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

                return
            assert not isinstance(target, Context) #TODO?
            worker = target.worker_ref()
            assert worker is not None #weakref may not be dead
            source._on_connect(target, worker, incoming = False)
            self.add_listener(source, target)

            if source._status == Cell.StatusFlags.OK:
                self.update_from_code(source, only_last=True)
            else:
                if isinstance(target, EditPinBase) and target.last_value is not None:
                    self.update_from_worker(
                        self.get_cell_id(source),
                        target.last_value,
                        worker, preliminary=False
                    )

        elif isinstance(source, OutputPinBase):
            assert isinstance(target, CellLike) and target._like_cell
            if isinstance(target, Context):
                assert "_input" in target._pins
                target = target._pins["_input"]
            if isinstance(source, ExportedOutputPin):
                source = source.get_pin()
            worker = source.worker_ref()
            assert worker is not None #weakref may not be dead
            target._on_connect(source, worker, incoming = True)
            cell_id = self.get_cell_id(target)
            if cell_id not in self.cells:
                self.cells[cell_id] = target

            if cell_id not in source._cell_ids:
                source._cell_ids.append(cell_id)
                if target not in self.cell_to_output_pin:
                    self.cell_to_output_pin[target] = []
                self.cell_to_output_pin[target].append(weakref.ref(source))

            if isinstance(worker, Transformer):
                worker._on_connect_output()
            elif source.last_value is not None:
                self.update_from_worker(
                    cell_id,
                    source.last_value,
                    worker,
                    preliminary=False
                )


        else:
            raise TypeError

import json
from ..dtypes.cson import cson2json
import weakref
from weakref import WeakKeyDictionary, WeakValueDictionary, WeakSet

#TODO: disconnect method (see MacroObject for low-level implementation)

class Manager:

    def __init__(self):
        self.listeners = {}
        self.macro_listeners = {}
        self.registrar_listeners = WeakKeyDictionary()
        self.rev_registrar_listeners = WeakKeyDictionary()
        self.pin_to_cells = {}
        self.cells = WeakValueDictionary()
        self.cell_to_output_pin = WeakKeyDictionary()
        self._childids = WeakValueDictionary()
        self.registrar_items = []
        self.unstable_processes = WeakSet()
        super().__init__()

    def set_stable(self, process, value):
        assert value in (True, False), value
        if not value:
            #print("UNSTABLE", process)
            self.unstable_processes.add(process)
        else:
            #print("STABLE", process)
            self.unstable_processes.discard(process)

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

    def _remove_listener(self, cell_id, input_pin, process):
        input_pin_id = input_pin.get_pin_id()
        l = self.listeners[cell_id]
        l[:] = [ref for ref in l if ref().get_pin_id() != input_pin_id]
        if not len(l):
            self.listeners.pop(cell_id)
            cell = self.cells.get(cell_id, None)
            if cell is not None:
                cell._on_disconnect(input_pin, process, False)

    def remove_listener(self, cell, input_pin):
        process = input_pin.process_ref()
        input_pin_id = input_pin.get_pin_id()
        cell_ids = self.pin_to_cells.pop(input_pin_id, [])
        cell_id = self.get_cell_id(cell)
        self._remove_listener(cell_id, input_pin, process)

    def remove_listeners(self, input_pin):
        process = input_pin.process_ref()
        cell_ids = self.pin_to_cells.pop(input_pin.get_pin_id(), [])
        for cell_id in cell_ids:
            self._remove_listener(cell_id, input_pin, process)

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


    def _update(self, cell_id, dtype, value, *, process=None, only_last=False):
        macro_listeners = self.macro_listeners.get(cell_id, [])

        if not only_last:
            for macro_object, macro_arg in macro_listeners:
                macro_object.update_cell(macro_arg)

        listeners = self.listeners.get(cell_id, [])
        if only_last:
            listeners = listeners[-1:]
        for input_pin_ref in listeners:
            input_pin = input_pin_ref()

            if input_pin is None:
                continue #TODO: error?

            if process is not None and input_pin.process_ref() is process:
                continue
            if (dtype == "cson" or dtype[0] == "cson") and \
              (input_pin.dtype == "json" or input_pin.dtype[0] == "json"):
                if isinstance(value, (str, bytes)):
                    value = cson2json(value)
            input_pin.receive_update(value)

    def update_from_code(self, cell, only_last=False):
        value = cell._data
        cell_id = self.get_cell_id(cell)
        self._update(cell_id, cell.dtype, value, only_last=only_last)
        from .. import run_work
        from .macro import get_macro_mode
        if not get_macro_mode():
            run_work()

    def update_from_process(self, cell_id, value, process):
        from .cell import Signal
        cell = self.cells.get(cell_id, None)
        if cell is None:
            return #cell has died...

        if isinstance(cell, Signal):
            assert value is None
            self._update(cell_id, None, None, process=process)
        else:
            changed = cell._update(value,propagate=False)
            if changed:
                self._update(cell_id, cell.dtype, value, process=process)

    def update_registrar_key(self, registrar, key):
        from .process import Process
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
            if isinstance(target, Process):
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
        from .process import EditPinBase, ExportedEditPin, \
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
            process = target.process_ref()
            if process is not None:
                source._on_disconnect(target, process, incoming = False)

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
                            self.cell_to_output_pin.remove(ref)
                            source._cell_ids.remove(cell_id)
                            ok = True
            if not ok:
                raise ValueError("Connection does not exist")

                if target not in self.cell_to_output_pin:
                    self.cell_to_output_pin[target] = []
                self.cell_to_output_pin[target].append(weakref.ref(source))

            if isinstance(process, Transformer):
                process._on_disconnect_output()

            process = source.process_ref()
            if process is not None:
                target._on_disconnect(source, process)

        else:
            raise TypeError

    def connect(self, source, target):
        from .transformer import Transformer
        from .cell import Cell, CellLike
        from .context import Context
        from .process import EditPinBase, ExportedEditPin, \
            InputPinBase, ExportedInputPin, OutputPinBase, ExportedOutputPin
        if isinstance(source, EditPinBase):
            source, target = target, source
        if isinstance(source, CellLike) and source._like_cell:
            assert isinstance(target, (InputPinBase, EditPinBase))
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
                self.update_from_code(source, only_last=True)

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
                if target not in self.cell_to_output_pin:
                    self.cell_to_output_pin[target] = []
                self.cell_to_output_pin[target].append(weakref.ref(source))

            if isinstance(process, Transformer):
                process._on_connect_output()

        else:
            raise TypeError

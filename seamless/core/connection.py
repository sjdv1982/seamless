import traceback

#TODO: a serialization protocol to establish data transfer over a cell-to-cell (alias) connection
# it depends on three variables:
# - the alias mode (argument to manager.connect_cell)
# - the type / some attribute of the source cell
# - the type / some attribute of the target cell

class Connection:
    #TODO: negotiate cell-to-cell serialization protocol
    def __init__(self, id, source, target):
        from .layer import Path
        self.id = id
        self.source = source #must be concrete, since connections are stored under the key "source"
        if isinstance(target, Path):
            self.target_path = target
            self.target = None
        else:
            self.target_path = None
            self.target = target

class CellToCellConnection(Connection):
    def __init__(self, id, source, target, alias_mode):
        super().__init__(id, source, target)
        if self.target is None:
            return
        if alias_mode is None:
            alias_mode = "ref"
        #TODO: extend to other connection types
        self.adapter = None
        if type(source) == type(target):
            return
        self.alias_mode = alias_mode
        source_modes = [m for m in source._supported_modes if m[0] == alias_mode \
         and m[1] is None and m[2] is not None]
        target_modes = [m for m in target._supported_modes if m[0] == alias_mode \
         and m[1] is None and m[2] is not None]
        self.adapter = select_adapter(source, target, source_modes, target_modes)

    def fire(self, only_text=False):
        #TODO: determine if with the target cell type, "only_text" warrants an update
        cell, target = self.source, self.target
        mode, submode = self.alias_mode, None
        value, _ = cell.serialize(mode, submode)
        if self.adapter:
            value = self.adapter(value)
        different, text_different = target.deserialize(value, mode, submode,
          #from_pin is set to True, also for aliases...
          from_pin=True, default=False
        )
        other = target._get_manager()
        if target._mount is not None:
            other.mountmanager.add_cell_update(target)
        if different or text_different:
            only_text_new = (text_different and not different)
            other.cell_send_update(target, only_text_new, None)

class CellToPinConnection(Connection):
    def __init__(self, id, source, target):
        super().__init__(id, source, target)
        if target is not None and not isinstance(target, Path):
            worker = target.worker_ref()
            assert worker is not None #weakref may not be dead
            source._check_mode(target.mode, target.submode) #TODO

    def fire(self, only_text=False):
        source, target = self.source, self.target
        value, checksum = source.serialize(target.mode, target.submode)
        if not only_text or target.submode == "text":
            target.receive_update(value, checksum)


class PinToCellConnection(Connection):
    def __init__(self, id, source, target):
        super().__init__(id, source, target)
        if source is not None and not isinstance(source, Path):
            worker = source.worker_ref()
            assert worker is not None #weakref may not be dead
            target._check_mode(source.mode, source.submode) #TODO

    def fire(self, value, preliminary):
        pin, cell = self.source, self.target
        cell._check_mode(pin.mode, pin.submode)
        mgr = pin._get_manager()
        other = cell._get_manager()
        if cell._destroyed or other.destroyed:
            return
        from_pin = "edit" if isinstance(pin, EditPin) else True
        try:
            different, text_different = cell.deserialize(value, pin.mode, pin.submode,
              from_pin=from_pin, default=False
            )
        except Exception:
            print("*** Error in setting %s ***" % cell)
            traceback.print_exc()
            print("******")
            return
        only_text = (text_different and not different)
        if text_different and cell._mount is not None:
            other.mountmanager.add_cell_update(cell)
        if different or text_different:
            other.cell_send_update(cell, only_text, origin=pin)

    def fire_reverse(self):
        pin, target = self.source, self.target
        target._check_mode(pin.mode, pin.submode)
        value, checksum = target.serialize(pin.mode, pin.submode)
        pin.receive_update(value, checksum)

from .worker import Worker, InputPin, EditPin, \
  InputPinBase, EditPinBase, OutputPinBase
from .layer import Path
from .protocol import select_adapter

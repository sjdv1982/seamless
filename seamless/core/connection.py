import traceback

#TODO: negotiate cell-to-cell serialization protocol (also in layer)

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
        self.alias_mode = alias_mode
    def fire(self, only_text=False):
        #TODO: negotiate proper serialization protocol (see cell.py, end of file)
        #TODO: determine if with the target cell type, "only_text" warrants an update
        cell, target = self.source, self.target
        mode, submode = self.alias_mode, None
        value, _ = cell.serialize(mode, submode)
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

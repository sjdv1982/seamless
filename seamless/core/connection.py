import traceback

#TODO: a serialization protocol to establish data transfer over a cell-to-cell (alias) connection
# it depends on three variables:
# - the transfer mode (argument to manager.connect_cell)
# - the type / some attribute of the source cell
# - the type / some attribute of the target cell

class Connection:
    source = None
    target = None
    transfer_mode = None
    source_access_mode = None
    source_content_type = None
    target_access_mode = None
    target_content_type = None
    adapter = None
    rev_adapter = None
    def __init__(self, id, source, target, transfer_mode,
      source_supported_modes, target_supported_modes
    ):
        from .layer import Path
        self.id = id
        self.source = source #must be concrete, since connections are stored under the key "source"
        if isinstance(target, Path):
            self.target_path = target
            self.target = None
        else:
            self.target_path = None
            self.target = target
        if self.target is None:
            return
        if transfer_mode is None:
            transfer_mode = "ref"
        self.adapter, modes = select_adapter(
         transfer_mode, source, target, source_supported_modes, target_supported_modes
        )
        source_mode, target_mode = modes
        assert source_mode[0] == target_mode[0]
        self.transfer_mode = source_mode[0]
        _, self.source_access_mode, self.source_content_type = source_mode
        _, self.target_access_mode, self.target_content_type = target_mode


class CellToCellConnection(Connection):
    def __init__(self, id, source, target, transfer_mode, duplex=False):
        source_supported_modes = source._supported_modes
        target_supported_modes = None
        if target is not None:
            target_supported_modes = target._supported_modes
        super().__init__(id, source, target, transfer_mode,
          source_supported_modes, target_supported_modes)
        self.duplex = duplex

    def fire(self, only_text=False):
        if only_text:
            if self.target_content_type not in ("text", "cson"):
                return
        #print("FIRE", self.source, ";", self.target, only_text)
        cell, target = self.source, self.target
        value = cell.serialize(
          self.transfer_mode, self.source_access_mode, self.source_content_type
        )
        """
        print(self.transfer_mode,
          self.source_access_mode, self.source_content_type,
          self.target_access_mode, self.target_content_type, type(value), self.adapter
        )
        """
        if self.adapter:
            value = self.adapter(value)
        #from_pin is set to True, also for aliases...
        #but not if duplex is True, meaning that we are two cells connected to each other
        from_pin = "duplex" if self.duplex else True
        different, text_different = target.deserialize(
          value,
          self.transfer_mode, self.target_access_mode, self.target_content_type,
          from_pin=from_pin, default=False
        )
        other = target._get_manager()
        if target._mount is not None:
            other.mountmanager.add_cell_update(target)
        if different or text_different:
            only_text_new = (text_different and not different)
            other.cell_send_update(target, only_text_new, None)

class CellToPinConnection(Connection):
    def __init__(self, id, source, target):
        source_supported_modes = source._supported_modes
        target_supported_modes = None
        transfer_mode  = None
        if target is not None and not isinstance(target, Path):
            worker = target.worker_ref()
            assert worker is not None #weakref may not be dead
            transfer_mode = target.transfer_mode
            target_supported_modes = [
              (transfer_mode,
               target.access_mode,
               target.content_type
              )
            ]
            if transfer_mode == "ref":
                target_supported_modes.append(
                  ("copy",
                   target.access_mode,
                   target.content_type
                  )
                )
        super().__init__(id, source, target, transfer_mode,
          source_supported_modes, target_supported_modes)

    def fire(self, only_text=False):
        source, target = self.source, self.target
        value = source.serialize(
          self.transfer_mode, self.source_access_mode, self.source_content_type
        )
        checksum = source.checksum()
        if self.adapter:
            value = self.adapter(value)
        if not only_text or self.target_access_mode == "text":
            target.receive_update(value, checksum, self.target_content_type)

class PinToCellConnection(Connection):
    def __init__(self, id, source, target):
        transfer_mode = source.transfer_mode
        if target is not None and not isinstance(target, Path):
            target_supported_modes = target._supported_modes

            worker = source.worker_ref()
            assert worker is not None #weakref may not be dead
            source_supported_modes = [
              (transfer_mode,
               source.access_mode,
               source.content_type
              )
            ]
            if transfer_mode == "ref":
                source_supported_modes.append(
                  ("copy",
                   source.access_mode,
                   source.content_type
                  )
                )
        super().__init__(id, source, target, transfer_mode,
          source_supported_modes, target_supported_modes)

    def fire(self, value, preliminary):
        pin, cell = self.source, self.target
        if self.adapter:
            value = self.adapter(value)

        mgr = pin._get_manager()
        other = cell._get_manager()
        if cell._destroyed or other.destroyed:
            return
        from_pin = "edit" if isinstance(pin, EditPin) else True
        try:
            different, text_different = cell.deserialize(
              value,
              self.transfer_mode, self.target_access_mode, self.target_content_type,
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

from .worker import Worker, InputPin, EditPin, \
  InputPinBase, EditPinBase, OutputPinBase
from .layer import Path
from .protocol import select_adapter

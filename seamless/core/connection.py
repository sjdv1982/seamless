#cell._check_mode(target.mode, target.submode)
#            worker = target.worker_ref()
#            assert worker is not None #weakref may not be dead

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

class CellToPinConnection(Connection):
    pass

class PinToCellConnection(Connection):
    pass

class Connection:
    pass

class CellToCellConnection(Connection):
    #TODO: negotiate cell-to-cell serialization protocol
    def __init__(self, id, source, target, alias_mode):
        from .layer import Path
        self.id = id
        self.source = source #must be concrete, since connections are stored under the key "source"
        if isinstance(target, Path):
            self.target_path = target
            self.target = None
        else:
            self.target_path = None
            self.target = target
        self.alias_mode = alias_mode

class CellToPinConnection(Connection):
    pass

class PinToCellConnection(Connection):
    pass

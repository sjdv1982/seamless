class Buffer:
    def __init__(self, value_or_buffer, celltype=None):
        from ..core.protocol.serialize import serialize_sync as serialize
        from ..core.protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum
        from ..core.cache.buffer_remote import write_buffer
        celltype = self._map_celltype(celltype)
        if celltype is None:
            if not isinstance(value_or_buffer, bytes):
                raise TypeError("Constructing Buffer from raw buffer, but raw buffer is not a bytes object")
            buf = value_or_buffer
        else:
            buf = serialize(value_or_buffer, celltype)
        checksum = calculate_checksum(buf)
        write_buffer(checksum, buf)
        self._value = buf
        self._checksum = checksum

    @staticmethod
    def _map_celltype(celltype):
        from ..core.cell import celltypes
        allowed_celltypes = list(celltypes.keys()) + ["silk", "deepcell", "deepfolder", "folder", "module"]
        if celltype is not None and celltype not in allowed_celltypes:
            raise TypeError(celltype, allowed_celltypes)
        if celltype == "silk":
            celltype = "mixed"
        elif celltype in ("deepcell", "deepfolder", "folder", "module"):
            celltype = "plain"
        return celltype

    @classmethod
    def load(cls, filename):
        """Loads the buffer from a file"""
        with open(filename, "rb") as f:
            buf = f.read()
        return cls(buf)

    @property
    def checksum(self):
        from .Checksum import Checksum
        return Checksum(self._checksum)

    @property
    def value(self):
        return self._value

    def save(self, filename):
        """Saves the buffer to a file"""
        if self.value is None:
            raise ValueError("Buffer is None")
        with open(filename, "wb") as f:
            f.write(self.value)

    def deserialize(self, celltype):
        from ..core.protocol.deserialize import deserialize_sync as deserialize
        if self.value is None:
            return None
        celltype = self._map_celltype(celltype)
        return deserialize(self.value, self.checksum.bytes(), celltype, copy=True)
    
    def __eq__(self, other):
        if not isinstance(other, Buffer):
            other = Buffer(other)
        return self.checksum == other.checksum

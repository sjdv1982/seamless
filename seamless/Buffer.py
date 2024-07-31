class Buffer:
    def __init__(self, value_or_buffer, celltype=None, *, checksum=None):
        from seamless import Checksum
        from seamless.buffer.serialize import serialize_sync as serialize
        celltype = self._map_celltype(celltype)
        if celltype is None:
            if isinstance(value_or_buffer, Buffer):
                value_or_buffer = value_or_buffer.value
            if not isinstance(value_or_buffer, bytes):
                raise TypeError("Constructing Buffer from raw buffer, but raw buffer is not a bytes object")
            buf = value_or_buffer
        else:
            buf = serialize(value_or_buffer, celltype)
        self._value = buf
        self._checksum = None
        if checksum:
            self._checksum = Checksum(checksum)

    @staticmethod
    def _map_celltype(celltype):
        if celltype is None:
            return None

        from seamless.buffer.cell import celltypes
        allowed_celltypes = celltypes + ["silk", "deepcell", "deepfolder", "folder", "module"]
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
        """Returns the buffer's Checksum object, which must have been calculated already"""
        from seamless import Checksum
        if self.value is not None and self._checksum is None:
            raise AttributeError("Checksum has not yet been calculated, use .get_checksum()")
        return Checksum(self._checksum)

    def get_checksum(self):
        """Returns the buffer's Checksum object, calculating it if needed"""
        from seamless.buffer.cached_calculate_checksum import cached_calculate_checksum_sync as cached_calculate_checksum
        if self._checksum is None:
            buf = self.value
            if buf is not None:
                checksum = cached_calculate_checksum(buf)
                self._checksum = checksum
        return self.checksum

    def upload(self):
        """Upload buffer to buffer write server (if defined)"""
        from seamless.buffer.buffer_remote import write_buffer
        self.get_checksum()
        write_buffer(self.checksum, self.value)

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
        from seamless.buffer.deserialize import deserialize_sync as deserialize
        if self.value is None:
            return None
        celltype = self._map_celltype(celltype)
        return deserialize(self.value, self.checksum.bytes(), celltype, copy=True)
    
    def __eq__(self, other):
        if not isinstance(other, Buffer):
            other = Buffer(other)
        return self.checksum == other.checksum

    def __len__(self):
        return len(self.value)
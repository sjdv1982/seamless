"""Class for Seamless buffers."""

from seamless import Checksum


class Buffer:
    """Class for Seamless buffers."""

    def __init__(
        self, value_or_buffer, celltype: str | None = None, *, checksum: Checksum = None
    ):
        from seamless.buffer.serialize import serialize_sync as serialize

        celltype = self._map_celltype(celltype)
        if celltype is None:
            if isinstance(value_or_buffer, Buffer):
                value_or_buffer = value_or_buffer.value
            if not isinstance(value_or_buffer, bytes):
                raise TypeError(
                    "Constructing Buffer from raw buffer, but raw buffer is not a bytes object"
                )
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

        allowed_celltypes = celltypes + [
            "deepcell",
            "deepfolder",
            "folder",
            "module",
        ]
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
    def checksum(self) -> Checksum:
        """Returns the buffer's Checksum object, which must have been calculated already"""
        if self.value is not None and self._checksum is None:
            raise AttributeError(
                "Checksum has not yet been calculated, use .get_checksum()"
            )
        return Checksum(self._checksum)

    def get_checksum(self) -> Checksum:
        """Returns the buffer's Checksum object, calculating it if needed"""
        from seamless.buffer.cached_calculate_checksum import (
            cached_calculate_checksum_sync as cached_calculate_checksum,
        )

        if self._checksum is None:
            buf = self.value
            if buf is not None:
                checksum = cached_calculate_checksum(buf)
                self._checksum = checksum
        return self.checksum

    async def get_checksum_async(self) -> Checksum:
        """Returns the buffer's Checksum object, calculating it asynchronously if needed"""
        from seamless.buffer.cached_calculate_checksum import cached_calculate_checksum

        if self._checksum is None:
            buf = self.value
            if buf is not None:
                checksum = await cached_calculate_checksum(buf)
                self._checksum = checksum
        return self.checksum

    def upload(self) -> None:
        """Upload buffer to buffer write server (if defined)"""
        from seamless.buffer.buffer_remote import write_buffer

        self.get_checksum()
        write_buffer(self.checksum, self.value)

    @property
    def value(self) -> bytes | None:
        """Return the buffer value"""
        return self._value

    def save(self, filename: str) -> None:
        """Saves the buffer to a file"""
        if self.value is None:
            raise ValueError("Buffer is None")
        with open(filename, "wb") as f:
            f.write(self.value)

    def deserialize(self, celltype: str):
        """Converts the buffer to a value.
        The checksum must have been computed already."""
        from seamless.buffer.deserialize import deserialize_sync as deserialize

        if self.value is None:
            return None
        celltype = self._map_celltype(celltype)
        return deserialize(self.value, self.checksum.bytes(), celltype, copy=True)

    async def deserialize_async(self, celltype: str, *, copy: bool = True):
        """Converts the buffer to a value.
        The checksum must have been computed already.

        If copy=False, the value can be returned from cache.
        It must not be modified.
        """
        from seamless.buffer.deserialize import deserialize

        if self.value is None:
            return None
        celltype = self._map_celltype(celltype)
        return await deserialize(self.value, self.checksum.bytes(), celltype, copy=copy)

    def __eq__(self, other):
        if not isinstance(other, Buffer):
            other = Buffer(other)
        return self.checksum == other.checksum

    def __len__(self):
        return len(self.value)
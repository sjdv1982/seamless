class Checksum:
    _value = None
    def __init__(self, checksum):
        from seamless.util import parse_checksum
        if isinstance(checksum, Checksum):
            self._value = checksum.bytes()
        else:
            self._value = parse_checksum(checksum, as_bytes=True)

    @classmethod
    def load(cls, filename):
        """Loads the checksum from a .CHECKSUM file.

If the filename doesn't have a .CHECKSUM extension, it is added"""
        if not filename.endswith(".CHECKSUM"):
            filename2 = filename + ".CHECKSUM"
        else:
            filename2 = filename
        with open(filename2, "rt") as f:
            checksum = f.read(100).rstrip()
        try:
            if len(checksum) != 64:
                raise ValueError
            self = cls(checksum)
        except (TypeError, ValueError):
            raise ValueError("File does not contain a SHA3-256 checksum") from None
        return self

    @property
    def value(self) -> str | None:
        return self.hex()
    
    def bytes(self) -> bytes | None:
        return self._value

    def hex(self) -> str | None:
        if self._value is None:
            return None
        return self._value.hex()

    def __eq__(self, other):
        if isinstance(other, bool):
            return bool(self) == other
        elif isinstance(other, int):
            return False
        if not isinstance(other, Checksum):
            other = Checksum(other)
        return self.bytes() == other.bytes()
        
    def save(self, filename):
        """Saves the checksum to a .CHECKSUM file.

If the filename doesn't have a .CHECKSUM extension, it is added"""
        if self.value is None:
            raise ValueError("Checksum is None")
        if not filename.endswith(".CHECKSUM"):
            filename2 = filename + ".CHECKSUM"
        else:
            filename2 = filename
        with open(filename2, "wt") as f:
            f.write(self.hex() + "\n")

    def resolve(self, celltype=None):
        """Returns the data buffer that corresponds to the checksum.
        If celltype is provided, a value is returned instead."""        
        from seamless.workflow.core.manager import Manager
        if celltype in (float, str, int, bool):
            celltype = celltype.__name__
        manager = Manager()
        return manager.resolve(self.hex(), celltype=celltype, copy=True)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return repr(self.value)

    def __hash__(self):
        return hash(self._value)

    def __bool__(self):
        return self._value is not None
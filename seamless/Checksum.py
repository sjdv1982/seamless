"""Class for Seamless checksums. Seamless checksums are calculated as SHA3-256 hashes of buffers."""

from typing import Union


class Checksum:
    """Class for Seamless checksums.
    Seamless checksums are calculated as SHA3-256 hashes of buffers."""

    _value: Union[bytes, None] = None  # pylint: disable=E0601

    def __init__(self, checksum: Union["Checksum", str, bytes, None]):
        from seamless.util import parse_checksum

        if isinstance(checksum, Checksum):
            self._value = checksum.bytes()
        else:
            self._value = parse_checksum(checksum, as_bytes=True)

    @classmethod
    def load(cls, filename: str) -> "Checksum":
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
        """Returns the checksum as a 64-byte hexadecimal string"""
        return self.hex()

    def bytes(self) -> bytes | None:
        """Returns the checksum as a 32-byte bytes object"""
        return self._value

    def hex(self) -> str | None:
        """Returns the checksum as a 64-byte hexadecimal string"""
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

    def __gt__(self, other):
        if isinstance(other, Checksum):
            return self._value > other._value
        elif isinstance(other, str):
            return self.hex() > other
        elif isinstance(other, bytes):
            return self._value > other
        else:
            raise NotImplementedError

    def __lt__(self, other):
        if isinstance(other, Checksum):
            return self._value < other._value
        elif isinstance(other, str):
            return self.hex() < other
        elif isinstance(other, bytes):
            return self._value < other
        else:
            raise NotImplementedError

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
        If celltype is provided, a value is returned instead.

        This imports seamless.workflow"""
        from seamless.workflow.core.manager import Manager

        if celltype in (float, str, int, bool):
            celltype = celltype.__name__
        manager = Manager()
        return manager.resolve(self.hex(), celltype=celltype, copy=True)

    async def resolution(self, celltype=None):
        """Returns the data buffer that corresponds to the checksum.
        If celltype is provided, a value is returned instead.

        This imports seamless.workflow"""
        from seamless.workflow.core.manager import Manager

        if celltype in (float, str, int, bool):
            celltype = celltype.__name__
        manager = Manager()
        return await manager.resolution(self.hex(), celltype=celltype, copy=True)

    def find(self, verbose: bool = False) -> list | None:
        """Returns a list of URL infos to download the underlying buffer.
        An URL info can be an URL string, or a dict with additional information."""
        from seamless.util.fair import find_url_info

        return find_url_info(self, verbose=verbose)

    def __str__(self):
        if self.value is None:
            return "<None>"
        return str(self.value)

    def __repr__(self):
        if self.value is None:
            return "<None>"
        return repr(self.value)

    def __hash__(self):
        return hash(self._value)

    def __bool__(self):
        return self._value is not None

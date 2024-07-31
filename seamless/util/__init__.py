from .pylru import lrucache
class lrucache2(lrucache):
    """Version of lrucache that can be disabled"""
    _disabled = False
    def disable(self):
        self._disabled = True
    def enable(self):
        del self._disabled
    def __setitem__(self, key, value):
        if self._disabled:
            return
        super().__setitem__(key, value)

def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string
If as_bytes is True, return it as bytes instead."""
    from seamless import Checksum
    if isinstance(checksum, Checksum):
        checksum = checksum.bytes()
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        if len(checksum) != 32:
            raise ValueError(f"Incorrect length: {len(checksum)}, must be 32")
        if as_bytes:
            return checksum
        else:
            return checksum.hex()
    
    if checksum is None:
        return
    raise TypeError(type(checksum))

from .cson import cson2json
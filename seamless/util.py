def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string"""
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        assert len(checksum) == 32, len(checksum)
        if as_bytes:
            return checksum
        else:
            return checksum.hex()
    
    if checksum is None:
        return
    raise TypeError(type(checksum))

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

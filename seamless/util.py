def parse_checksum(checksum):
    """Parses checksum and returns it as string"""
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        assert len(checksum) == 32, len(checksum)
        return checksum.hex()
    elif checksum is None:
        pass
    else:
        raise TypeError(type(checksum))

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

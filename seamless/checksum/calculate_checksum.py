"""Calculate SHA3-256 checksums"""

from hashlib import sha3_256


def calculate_checksum(
    content: bytes, hex: bool = False
):  # pylint: disable=redefined-builtin
    """Calculate a SHA3-256 checksum.
    If hex, return it as hexidecimal string, else as bytes object"""
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hasher = sha3_256(content)
    result = hasher.digest()
    if hex:
        result = result.hex()
    return result


def calculate_file_checksum(filename: str) -> str:
    """Calculate a file checksum"""
    blocksize = 2**16
    with open(filename, "rb") as f:
        hasher = sha3_256()
        while 1:
            block = f.read(blocksize)
            if not block:
                break
            hasher.update(block)
    checksum = hasher.digest().hex()
    return checksum


def calculate_dict_checksum(d: dict, hex=False):  # pylint: disable=redefined-builtin
    """This function is compatible with the checksum of a "plain" cell"""
    from seamless.checksum.json import json_dumps

    content = json_dumps(d, as_bytes=True) + b"\n"
    return calculate_checksum(content, hex=hex)

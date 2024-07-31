from hashlib import sha3_256
import json

def calculate_checksum(content, hex=False):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    result = hash.digest()
    if hex:
        result = result.hex()
    return result

def calculate_file_checksum(filename: str) -> str:
    """Calculate a file checksum"""
    blocksize = 2**16
    with open(filename, "rb") as f:
        hash = sha3_256()
        while 1:
            block = f.read(blocksize)
            if not block:
                break
            hash.update(block)
    checksum = hash.digest().hex()
    return checksum

def calculate_dict_checksum(d, hex=False):
    """This function is compatible with the checksum of a "plain" cell"""
    from seamless.workflow.core.protocol.json import json_dumps
    content = json_dumps(d, as_bytes=True) + b"\n"
    return calculate_checksum(content,hex=hex)
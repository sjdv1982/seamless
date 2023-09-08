from hashlib import sha3_256
import json

# Code adapted from the Seamless project, copyright 2016-2023 INSERM, CNRS.


def calculate_checksum(content):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    result = hash.digest()
    result = result.hex()
    return result


def calculate_dict_checksum(d):
    """This function is compatible with the checksum of a "plain" cell"""
    from seamless.core.protocol.json import json_dumps

    content = json.dumps(d, as_bytes=True) + b"\n"
    return calculate_checksum(content)

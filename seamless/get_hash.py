from hashlib import sha3_256
import json

def get_hash(content, hex=False):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    result = hash.digest()
    if hex:
        result = result.hex()
    return result

def get_dict_hash(d, hex=False):
    content = json.dumps(d, sort_keys=True, indent=2) + "\n"
    return get_hash(content,hex=hex)
from hashlib import sha3_256
def get_hash(content, *, hex):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    if hex:
        return hash.hexdigest()
    else:
        return hash.digest()
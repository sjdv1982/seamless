import json
import numpy as np
from .to_stream import to_stream
from .from_stream import from_stream

MAGIC_SEAMLESS_MIXED = b'\x94SEAMLESS-MIXED'
def serialize(data, *, storage=None, form=None):
    from ..get_form import get_form
    if storage is None or form  is None:
        storage, form = get_form(data)
    content = to_stream(data, storage, form)
    if storage in ("pure-plain", "pure-binary"):
        return content
    result = MAGIC_SEAMLESS_MIXED
    h1 = storage.encode()
    result += np.uint8(len(h1)).tobytes()
    result += h1
    h2 = json.dumps(form).encode()
    result += np.uint32(len(h2)).tobytes()
    result += h2
    result += content    
    return result

def deserialize(data):
    from .. import MAGIC_SEAMLESS
    from .from_stream import MAGIC_NUMPY
    from ..get_form import get_form
    pure_plain, pure_binary = False, False
    if isinstance(data, str):
        pure_plain = True            
    if not pure_plain:
        assert isinstance(data, bytes)
        if data.startswith(MAGIC_NUMPY):
            pure_binary = True
        elif not data.startswith(MAGIC_SEAMLESS_MIXED):
            pure_plain = True
    if pure_plain or pure_binary:        
        mode = "pure-plain" if pure_plain else "pure-binary"
        if pure_plain and not isinstance(data, str):
            assert not data.startswith(MAGIC_SEAMLESS) #TODO: cache seems to have stored stream instead of mixed stream...
            data = data.decode()
        value = from_stream(data, mode, None)
        _, form = get_form(value)
        return value, mode, form

    offset = len(MAGIC_SEAMLESS_MIXED)
    lh1 = np.frombuffer(data[offset:offset+1], np.uint8)[0]
    offset += 1
    h1 = data[offset:offset+lh1]
    offset += lh1
    lh2 = np.frombuffer(data[offset:offset+4], np.uint32)[0]
    offset += 4
    h2 = data[offset:offset+lh2]
    offset += lh2
    storage = h1.decode()
    form = json.loads(h2.decode())
    return from_stream(data[offset:], storage, form), storage, form
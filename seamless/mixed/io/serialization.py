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
    if isinstance(data, str):
        return from_stream(data, "pure-plain", None), "pure-plain", None
    assert isinstance(data, bytes)
    if data.startswith(MAGIC_NUMPY):
        return from_stream(data, "pure-binary", None), "pure-binary", None
    elif not data.startswith(MAGIC_SEAMLESS_MIXED):
        return from_stream(data.decode(), "pure-plain", None), "pure-plain", None
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
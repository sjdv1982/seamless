from ...cell import cell
from . import MAGIC_SEAMLESS_REQUEST
import numpy as np
import json

nil = json.dumps(None)

def encode(transformer_params, output_signature, values, access_modes, content_types):
    #TODO: SHA-512 checksums
    assert values.keys() == content_types.keys() == access_modes.keys()
    b = b''
    d = [transformer_params, output_signature]
    for k in values:
        v = values[k]
        c = content_types[k]
        am = access_modes[k]
        cc = cell(c)
        cc.deserialize(v, "ref", am, c, from_pin=False, default=False)
        if cc._val is None:
            buf = nil
        else:
            buf = cc.serialize_buffer()
        ma = cc._mount_kwargs
        binary = ma["binary"]
        encoding = ma.get("encoding")
        if not isinstance(buf, bytes):
            buf = buf.encode(encoding)
        d.append((k,am,c,len(buf)))
        b += buf
    dd = json.dumps(d)

    s1 = np.uint64(len(dd)).tobytes()
    s2 = np.uint64(len(b)).tobytes()
    streamsize = len(MAGIC_SEAMLESS_REQUEST) + 16 + len(dd) + len(b)
    stream = bytearray(streamsize)
    l = len(MAGIC_SEAMLESS_REQUEST)
    stream[:l] = MAGIC_SEAMLESS_REQUEST
    stream[l:l+8] = s1
    stream[l+8:l+16] = s2
    stream[l+16:l+16+len(dd)] = dd.encode()
    stream[l+16+len(dd):streamsize] = b
    return stream

from . import MAGIC_SEAMLESS_REQUEST
from ...cell import cell
from io import StringIO
import numpy as np
import json

def decode(rqdata, as_cells=False):
    assert isinstance(rqdata, bytes)
    assert rqdata.startswith(MAGIC_SEAMLESS_REQUEST)
    l = len(MAGIC_SEAMLESS_REQUEST)
    s1 = rqdata[l:l+8]
    s2 = rqdata[l+8:l+16]
    len_dd = np.frombuffer(s1, dtype=np.uint64).tolist()[0]
    len_b = np.frombuffer(s2, dtype=np.uint64).tolist()[0]

    values, access_modes, content_types = {}, {}, {}
    #TODO: SHA-512 checksums
    dd = rqdata[l+16:l+16+len_dd].decode()
    d = json.loads(dd)
    b = rqdata[l+16+len_dd:]
    assert len(b) == len_b

    pos = 0
    transformer_params, output_signature = d[:2]
    for k,am,c,len_buf in d[2:]:
        access_modes[k] = am
        content_types[k] = c
        buf = b[pos:pos+len_buf]
        cc = cell(c)
        ma = cc._mount_kwargs
        binary = ma["binary"]
        encoding = ma.get("encoding")
        if not binary:
            buf = buf.decode(encoding)
        cc.deserialize(buf, "buffer", am, c, from_pin=False, default=False)
        if as_cells:
            values[k] = cc
        else:
            val = cc.serialize("ref", am, c)
            values[k] = val
        pos += len(buf)
    return transformer_params, output_signature, values, access_modes, content_types

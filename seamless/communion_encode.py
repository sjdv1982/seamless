"""
Encoding/decoding of communion messages

message must be a dict containing:
    "mode": "request" or "response"
    "id": 32-bit identifier, should increase
    "content": None, bool, bytes, str, int, float, or tuple of str/int/float/bool
    remaining keys: anything JSON-serializable
encoded message is binary, and consists of:
header SEAMLESS
tip: 0 for request, 1 for response
identifier: 32-bit
nrem: 32-bit, the length of the remaining keys buffer (after content)
content: is_str byte + remainder. For is_str:
  0:  No remainder, message is None
  1:  bool. remainder is 0 or 1
  2:  bytes. remainder is raw content
  3:  str. remainder is UTF-8 encoded content
  4:  int/float/tuple. remainder is JSON-encoded content.
rem: remaining keys buffer (JSON format)
"""

import numpy as np
import json

def communion_encode(msg):
    assert msg["mode"] in ("request", "response")
    m = 'SEAMLESS'.encode()
    tip = b'\x00' if msg["mode"] == "request" else b'\x01'
    m += tip

    m += np.uint32(msg["id"]).tobytes()
    remainder = msg.copy()
    remainder.pop("mode")
    remainder.pop("id")
    remainder.pop("content")
    if len(remainder.keys()):
        rem = json.dumps(remainder).encode()
        nrem = np.uint32(len(rem)).tobytes()
        m += nrem
        m += rem
    else:
        m += b'\x00\x00\x00\x00'
    content = msg["content"]
    if content is None:
        m += b'\x00'
    else:
        assert isinstance(content, (str, int, float, bytes, bool, tuple)), content
        if isinstance(content, bool):
            is_str = b'\x01'
        elif isinstance(content, (int, float, tuple)):
            is_str = b'\x04'
        else:
            is_str = b'\x03' if isinstance(content, str) else b'\x02'
        m += is_str
        if isinstance(content, str):
            content = content.encode()
        elif isinstance(content, bool):
            content = b'\x01' if content else b'\x00'
        elif isinstance(content, (int, float, tuple)):
            if isinstance(content, tuple):
                for item in content:
                    assert item is None or isinstance(item, (str, int, float, bool)), type(item)
            content = json.dumps(content).encode()
        m += content
    assert communion_decode(m) == msg, (communion_decode(m), msg)
    return m

def communion_decode(m):
    assert isinstance(m, bytes)
    message = {}
    head = 'SEAMLESS'.encode()
    assert m[:len(head)] == head
    m = m[len(head):]
    tip = m[:1]
    m = m[1:]
    assert tip == b'\x01' or tip == b'\x00', tip
    message["mode"] = "request" if tip == b'\x00' else "response"
    l1, l2 = m[:4], m[4:8]
    m = m[8:]
    message["id"] = np.frombuffer(l1,np.uint32)[0]
    nrem = np.frombuffer(l2,np.uint32)[0]
    if nrem:
        rem = m[:nrem]
        rem = rem.decode()
        rem = json.loads(rem)
        message.update(rem)
        m = m[nrem:]
    is_str = m[:1]
    if is_str == b'\x00':
        content = None
    elif is_str == b'\x01':
        content = True if m[1:] == b'\x01' else False
    elif is_str == b'\x04':
        content = json.loads(m[1:])
        assert isinstance(content, (int, float, list))
        if isinstance(content, list):
            for item in content:
                assert item is None or isinstance(item, (str, int, float, bool)), type(item)
            content = tuple(content)
    else:
        assert is_str == b'\x03' or is_str == b'\x02'
        content = m[1:]
        if is_str == b'\x03':
            content = content.decode()
    message["content"] = content
    return message

import seamless
seamless.delegate(False)

from seamless.workflow import Context, DeepCell, Cell
from seamless.workflow.core.protocol.serialize import serialize_sync as serialize
from seamless.workflow.core.cache.buffer_cache import buffer_cache
from seamless import calculate_checksum
import json
import requests

options = {
    "option_a": {
        "checksum": {
            "x": 10,
            "y": [20,30,40],
            "z": {"p": 50, "q": 60}
        },
        "keyorder": ["y", "z", "x"]
    },
    "option_b": {
        "checksum": {
            "xx": 110,
            "yy": [120,130,-40],
            "zz": {"p": -50, "q": 160}
        },
        "keyorder": ["yy", "zz", "xx"]
    },
    "option_x": {
        "checksum": {
            "v1": "string A",
            "v2": "string B",
            "v3": "string C",
        },
        "keyorder": ["v1", "v2", "v3"]
    },
}
options2 = {}
for k in options:
    opt = options[k]
    opt2 = {}
    
    v = opt["keyorder"]
    buf = serialize(v, "mixed")
    checksum = calculate_checksum(buf,hex=True)
    buffer_cache.cache_buffer(bytes.fromhex(checksum), buf)
    opt2["keyorder"] = checksum

    v = opt["checksum"]
    opt3 = {}
    for kk, vv in v.items():
        buf = serialize(vv, "mixed")
        checksum = calculate_checksum(buf,hex=True)
        buffer_cache.cache_buffer(bytes.fromhex(checksum), buf)
        opt3[kk] = checksum
    opt3_buf = serialize(opt3, "plain")
    checksum = calculate_checksum(opt3_buf,hex=True)
    buffer_cache.cache_buffer(bytes.fromhex(checksum), opt3_buf)
    opt2["checksum"] = checksum

    options2[k] = opt2
print(json.dumps(options2, sort_keys=True, indent=2))

ctx = Context()
ctx.c = DeepCell()
ctx.c.share(options=options2)
ctx.cc = Cell()
ctx.cc.hash_pattern = {"*": "#"}
ctx.cc = ctx.c
ctx.compute()
print("Stage 1")
ctx.c.define(options2["option_x"])
ctx.compute()
print(ctx.c.status)
print(ctx.c.exception)
print(1, ctx.c._get_context().origin0.value)
print(2, ctx.c._get_context().origin02.value)
print(3, ctx.c._get_context().origin03.value)
print(4, ctx.c._get_context().origin04.value)
print(5, ctx.c._get_context().origin_integrated0.value)
print(6, ctx.c._get_context().origin_integrated.value)
print(7, options["option_x"]["checksum"])
print(ctx.c._get_context().selected_option.value)
print(ctx.cc.value)
print()
print("Stage 2")
ctx.c._get_context().selected_option.set("option_a")
ctx.compute()
print(ctx.c.status)
print(ctx.c.exception)
print(1, ctx.c._get_context().origin0.value)
print(2, ctx.c._get_context().origin02.value)
print(3, ctx.c._get_context().origin03.value)
print(4, ctx.c._get_context().origin04.value)
print(5, ctx.c._get_context().origin_integrated0.value)
print(6, ctx.c._get_context().origin_integrated.value)
print(7, options["option_a"]["checksum"])
print(ctx.c._get_context().selected_option.value)
print(ctx.cc.value)
print()
print("Stage 3")

import asyncio
loop = asyncio.get_event_loop()
def thread(func, *args, **kwargs):
    from threading import Thread
    from queue import Queue
    def func2(func, q, args, kwargs):
        result = func(*args, **kwargs)
        q.put(result)
    q = Queue()
    t = Thread(target=func2, args=(func, q, args, kwargs))
    t.start()
    while t.is_alive():
        t.join(0.05)
        loop.run_until_complete(asyncio.sleep(0.01))
    return q.get()

r = thread(requests.get, 'http://localhost:5813/ctx/c/OPTIONS')
print(r.json())
print()
r = thread(requests.get, 'http://localhost:5813/ctx/c/SELECTED_OPTION')
print(r.text)
"""
import logging
logging.basicConfig()
logging.getLogger("seamless").setLevel(logging.DEBUG)
"""
r = thread(
    requests.put, 'http://localhost:5813/ctx/c/SELECTED_OPTION',
    data=json.dumps({"buffer": "option_b"})
)
print(r.text)
print()
ctx.compute()
print(ctx.c.status)
print(ctx.c.exception)
print(1, ctx.c._get_context().origin0.value)
print(2, ctx.c._get_context().origin02.value)
print(3, ctx.c._get_context().origin03.value)
print(4, ctx.c._get_context().origin04.value)
print(5, ctx.c._get_context().origin_integrated0.value)
print(6, ctx.c._get_context().origin_integrated.value)
print(7, options["option_a"]["checksum"])
print(ctx.c._get_context().selected_option.value)
print(ctx.cc.value)
print()
r = thread(requests.get, 'http://localhost:5813/ctx/c/SELECTED_OPTION')
print(r.text)

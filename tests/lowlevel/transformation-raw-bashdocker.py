import inspect, textwrap

import seamless
seamless.delegate(False)

from seamless import calculate_checksum
from seamless.core.cache.buffer_cache import buffer_cache
from seamless.core.cache.transformation_cache import (
    transformation_cache, DummyTransformer, tf_get_buffer, 
    syntactic_is_semantic, syntactic_to_semantic, 
    transformation_cache
)

from seamless.core.protocol.serialize import serialize

async def build_transformation():
    bash_code = "nginx -v"
    inp = {
        "code": ("text", bash_code),
        "__env__": ("plain", {"docker": {"name": "nginx:1.25.2"}}),
    }
    tf_dunder = {}
    transformation = {
        "__language__": "bash",
        "__output__": ("result", "bytes", None)
    }
    for k,v in inp.items():
        celltype, value = v
        buf = await serialize(value, celltype)
        checksum = calculate_checksum(buf)
        buffer_cache.cache_buffer(checksum, buf)
        if k == "__env__":
            tf_dunder[k] = checksum.hex()
        else:
            transformation[k] = celltype, None, checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    tf_checksum = calculate_checksum(tf_buf)
    buffer_cache.cache_buffer(tf_checksum, tf_buf)
    
    tf = DummyTransformer(tf_checksum)
    result = await transformation_cache.run_transformation_async(tf_checksum, tf_dunder=tf_dunder, fingertip=False)
    if result is not None:
        result = buffer_cache.get_buffer(result, remote=False)
    if result is not None:
        try:
            result = result.decode()
        except UnicodeDecodeError:
            pass
    print(result)

import asyncio
asyncio.get_event_loop().run_until_complete(build_transformation())
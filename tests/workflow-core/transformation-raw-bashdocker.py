import os

import seamless

from seamless import Checksum, Buffer
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum.buffer_remote import (
    write_buffer as remote_write_buffer,
)

from seamless.util.transformation import tf_get_buffer
from seamless.workflow.core.cache.transformation_cache import transformation_cache

if "DELEGATE" in os.environ:
    delegation = True
    seamless.delegate()
else:
    delegation = False
    seamless.delegate(False)


async def build_transformation():
    bash_code = "nginx -v >& RESULT"
    inp = {
        "code": ("text", bash_code),
        "__env__": ("plain", {"docker": {"name": "nginx:1.25.2"}}),
    }
    tf_dunder = {}
    transformation = {"__language__": "bash", "__output__": ("result", "bytes", None)}
    for k, v in inp.items():
        celltype, value = v
        buf = await Buffer.from_async(value, celltype)
        checksum = await buf.get_checksum_async()
        buffer_cache.cache_buffer(checksum, buf)
        remote_write_buffer(checksum, buf)
        if k == "__env__":
            tf_dunder[k] = checksum.hex()
        else:
            transformation[k] = celltype, None, checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    tf_checksum = await Buffer(tf_buf).get_checksum_async()
    print(tf_buf.decode())
    buffer_cache.cache_buffer(tf_checksum, tf_buf)
    remote_write_buffer(tf_checksum, tf_buf)

    result = None
    result_checksum = await transformation_cache.run_transformation_async(
        tf_checksum, tf_dunder=tf_dunder, fingertip=False, scratch=False
    )
    result_checksum = Checksum(result_checksum)
    if result_checksum:
        result = buffer_cache.get_buffer(result_checksum, remote=(delegation == True))
        if delegation:
            transformation_cache.undo(tf_checksum)
    if result is not None:
        try:
            result = result.decode()
        except UnicodeDecodeError:
            pass
    print(result)


import asyncio

asyncio.get_event_loop().run_until_complete(build_transformation())

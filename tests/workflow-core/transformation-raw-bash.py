import seamless

seamless.delegate(False)

from seamless import Checksum, Buffer
from seamless.checksum.buffer_cache import buffer_cache
from seamless.util.transformation import tf_get_buffer
from seamless.workflow.core.cache.transformation_cache import (
    transformation_cache,
    DummyTransformer,
    transformation_cache,
)


async def build_transformation():
    bash_code = """awk -v a=$a -v b=$b 'BEGIN{print("OK?", a, b, a+b)}' > RESULT"""
    inp = {
        "a": (
            "int",
            12,
        ),
        "b": (
            "int",
            7,
        ),
        "code": ("text", bash_code),
    }
    transformation = {"__language__": "bash", "__output__": ("result", "bytes", None)}
    for k, v in inp.items():
        celltype, value = v
        buf = await Buffer.from_async(value, celltype)
        checksum = await buf.get_checksum_async()
        buffer_cache.cache_buffer(checksum, buf)
        transformation[k] = celltype, None, checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    print(tf_buf.decode())
    tf_checksum = await Buffer(tf_buf).get_checksum_async()
    buffer_cache.cache_buffer(tf_checksum, tf_buf)

    tf = DummyTransformer(tf_checksum)
    result = await transformation_cache.run_transformation_async(
        tf_checksum, fingertip=False, scratch=False
    )
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

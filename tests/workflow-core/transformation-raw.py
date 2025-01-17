import seamless

seamless.delegate(False)

import inspect, textwrap

from seamless import Buffer
from seamless.checksum.buffer_cache import buffer_cache
from seamless.util.transformation import tf_get_buffer
from seamless.workflow.core.cache.transformation_cache import (
    transformation_cache,
    DummyTransformer,
    syntactic_is_semantic,
    syntactic_to_semantic,
    transformation_cache,
)


def func(a, b):
    return a * b + 1000


def get_source(value):
    if callable(value):
        value = inspect.getsource(value)
    if value is not None:
        value = textwrap.dedent(value)
    return value


async def get_semantic_checksum(checksum, celltype, pinname):
    subcelltype = None
    if not syntactic_is_semantic(celltype, subcelltype):
        sem_checksum = await syntactic_to_semantic(
            checksum, celltype, subcelltype, pinname
        )
        semkey = (sem_checksum, celltype, subcelltype)
        transformation_cache.semantic_to_syntactic_checksums[semkey] = [checksum]
    else:
        sem_checksum = checksum
    return sem_checksum


async def build_transformation():
    func_buf = (
        await Buffer.from_async(get_source(func) + "\nresult = func(a,b)", "python")
    ).value
    inp = {
        "a": (
            "int",
            12,
        ),
        "b": (
            "int",
            7,
        ),
        "code": ("python", func_buf),
    }
    transformation = {"__language__": "python", "__output__": ("result", "int", None)}
    for k, v in inp.items():
        celltype, value = v
        buf = await Buffer.from_async(value, celltype)
        checksum = await buf.get_checksum_async()
        buffer_cache.cache_buffer(checksum, buf)
        sem_checksum = await get_semantic_checksum(checksum, celltype, k)
        transformation[k] = celltype, None, sem_checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    print(tf_buf.decode())
    tf_checksum = await Buffer(tf_buf).get_checksum_async()
    buffer_cache.cache_buffer(tf_checksum, tf_buf)

    tf = DummyTransformer(tf_checksum)
    result = await transformation_cache.run_transformation_async(
        tf_checksum, fingertip=False, scratch=False
    )
    print(buffer_cache.get_buffer(result, remote=False))


import asyncio

asyncio.get_event_loop().run_until_complete(build_transformation())

import seamless

seamless.delegate(False)

import inspect, textwrap

from seamless import Buffer
from seamless.checksum.buffer_cache import buffer_cache
from seamless.workflow.core.cache.transformation_cache import (
    transformation_cache,
    DummyTransformer,
    tf_get_buffer,
    syntactic_is_semantic,
    syntactic_to_semantic,
    transformation_cache,
)


def func(a, b):
    import tensorflow as tf

    t = tf.add(tf.multiply(a, b), 1000)
    return t.numpy()


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
    environment = {
        "conda": {
            "dependencies": [
                "tensorflow>=2",
            ]
        }
    }
    for k, v in inp.items():
        celltype, value = v
        buf = await Buffer.from_async(value, celltype)
        checksum = await buf.get_checksum_async()
        buffer_cache.cache_buffer(checksum, buf)
        sem_checksum = await get_semantic_checksum(checksum, celltype, k)
        transformation[k] = celltype, None, sem_checksum.hex()

    envbuf = await Buffer.from_async(environment, "plain")
    env_checksum = await envbuf.get_checksum_async()
    buffer_cache.cache_buffer(env_checksum, envbuf)
    transformation["__env__"] = env_checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    print(tf_buf.decode())
    tf_checksum = await Buffer(tf_buf).get_checksum_async()
    buffer_cache.cache_buffer(tf_checksum, tf_buf)

    tf = DummyTransformer(tf_checksum)
    result = await transformation_cache.run_transformation_async(
        tf_checksum, scratch=False, fingertip=False
    )
    print(transformation_cache.transformation_exceptions.get(tf_checksum))
    print(buffer_cache.get_buffer(result, remote=False))


import asyncio

asyncio.get_event_loop().run_until_complete(build_transformation())

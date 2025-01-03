import json
import seamless

seamless.delegate(False)

from seamless import Checksum, Buffer
from seamless.checksum.buffer_cache import buffer_cache
from seamless.util.transformation import tf_get_buffer
from seamless.workflow.core.cache.transformation_cache import (
    transformation_cache,
    syntactic_is_semantic,
    syntactic_to_semantic,
    transformation_cache,
)

from seamless.util.ipython import ipython2python

func_code = """
%%timeit
def func(a,b):
    import time
    time.sleep(0.05)
    return a + b

result = a + b
"""

func_code = ipython2python(func_code)


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
    func_buf = (await Buffer.from_async(func_code, "python")).value
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
    tf_dunder = {}
    transformation = {
        "__language__": "bash",
        "__output__": ("result", "bytes", None),
    }

    transformation = {"__language__": "python", "__output__": ("result", "int", None)}
    environment = {"powers": ["ipython"]}
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
    transformation["__env__"] = (
        env_checksum.hex()
    )  # will be ignored; tf_dunder is needed
    tf_dunder["__env__"] = env_checksum.hex()

    tf_buf = tf_get_buffer(transformation)
    print(tf_buf.decode())
    print(json.dumps(tf_dunder, sort_keys=True, indent=2))
    tf_checksum = await Buffer(tf_buf).get_checksum_async()
    buffer_cache.cache_buffer(tf_checksum, tf_buf)

    result = await transformation_cache.run_transformation_async(
        tf_checksum, tf_dunder=tf_dunder, fingertip=False, scratch=False
    )
    print(buffer_cache.get_buffer(result, remote=False))
    print(transformation_cache.transformation_logs[tf_checksum])


import asyncio

asyncio.get_event_loop().run_until_complete(build_transformation())

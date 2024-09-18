import seamless
from seamless import Checksum, Buffer
import asyncio

value = {"a": 10, "b": 11, "c": 88, "d": [5, 6, 8], "e": "Text"}

buf = Buffer(value, celltype="plain")
print(buf)
print()
print(buf.deserialize("plain"))

cs = buf.get_checksum()
print(cs)
print()

seamless.delegate(False)
print(cs.resolve())
print(cs.resolve(celltype="plain"))
print()


def run(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


print(run(cs.resolution()))
print(run(cs.resolution(celltype="plain")))
print()

from seamless.checksum import empty_dict_checksum

cs = Checksum(empty_dict_checksum)
print(run(cs.resolution()))
print(run(cs.resolution(celltype="plain")))

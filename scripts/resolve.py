import sys
import seamless
from seamless.core.protocol.deserialize import _deserialize as deserialize_sync
cache = seamless.RedisCache()
checksum = bytes.fromhex(sys.argv[1])
buffer = cache.get_buffer(checksum)
if buffer is None:
    print(None)
    sys.exit()
if len(sys.argv) > 2:
    celltype = sys.argv[2]
    value = deserialize_sync(buffer, checksum, celltype)
    print(value)
else:
    print(buffer)
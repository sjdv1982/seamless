import sys
import seamless
from seamless.core.protocol.deserialize import _deserialize as deserialize_sync
seamless.database_cache.connect()
checksum = bytes.fromhex(sys.argv[1])
buffer = seamless.database_cache.get_buffer(checksum)
if buffer is None:
    print(None)
    sys.exit()
if len(sys.argv) > 2:
    celltype = sys.argv[2]
    value = deserialize_sync(buffer, checksum, celltype)
    print(value)
else:
    print(buffer)
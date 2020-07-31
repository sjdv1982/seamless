import sys
checksum = sys.argv[1]
checksum = bytes.fromhex(checksum)

import seamless
seamless.database_sink.connect()
seamless.database_cache.connect()

result = seamless.run_transformation(checksum)
if result is not None:
    result = result.hex()
print(result)
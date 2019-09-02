import sys
checksum = sys.argv[1]
checksum = bytes.fromhex(checksum)

import seamless
cache = seamless.RedisCache()
sink = seamless.RedisSink()

result = seamless.run_transformation(checksum)
if result is not None:
    result = result.hex()
print(result)    
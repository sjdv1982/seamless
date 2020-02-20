import sys
import seamless
cache = seamless.RedisCache()
checksum = bytes.fromhex(sys.argv[1])
key = "tfr:" + checksum.hex()
redis = cache.connection
if redis.exists(key):
    redis.delete(key)
    print("Transformation result deleted")
else:
    print("Transformation result not found")
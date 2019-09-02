import sys
import seamless
cache = seamless.RedisCache()
checksum = bytes.fromhex(sys.argv[1])
key = b"tfr:" + checksum
redis = cache.connection
if redis.exists(key):
    redis.delete(key)
    print("Transformation result deleted")
else:
    print("Transformation result not found")